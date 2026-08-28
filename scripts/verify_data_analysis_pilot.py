#!/usr/bin/env python3
"""Run and verify the deterministic sample-data analysis pilot."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

REQUIRED_COLUMNS = (
    "week_start",
    "channel",
    "sessions",
    "signups",
    "paid_conversions",
)
ALLOWED_CHANNELS = {"organic", "ads"}
CHANNEL_ORDER = ("organic", "ads")
SNAPSHOT_DATE = date(2026, 8, 24)
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "data-analysis"
REPORT_HEADINGS = (
    "## Source and quality gate",
    "## Observations",
    "## Calculations",
    "## Inferences",
    "## Recommendations",
    "## Unknowns",
    "## Publication boundary",
)
REPORT_TABLES = (
    ("| Period | Sessions | Paid conversions | Paid conversion rate |", 4),
    ("| Channel | Prior rate | Current rate | Change |", 4),
)
UNSAFE_LOCAL_PATH_MARKERS = ("/Users/", "/home/", "C:\\Users\\")


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def public_source_label(source: Path) -> str:
    """Return a repository-relative source label without exposing local paths."""

    resolved = source.resolve()
    try:
        relative = resolved.relative_to(REPOSITORY_ROOT)
    except ValueError:
        return "<external source>"
    label = relative.as_posix()
    if any(character in label for character in ("`", "\r", "\n")):
        return "<source label withheld>"
    return label


def _table_column_count(row: str) -> int:
    if not row.startswith("|") or not row.endswith("|"):
        return 0
    return len(row.split("|")[1:-1])


def validate_report_layout(report: str) -> None:
    """Check the stable Markdown structure used by the reviewed pilot report."""

    lines = report.splitlines()
    if not report.endswith("\n"):
        fail("generated report must end with a newline")
    headings = tuple(line for line in lines if line.startswith("## "))
    if headings != REPORT_HEADINGS:
        fail(f"unexpected report heading order: {headings}")

    heading_positions = [lines.index(heading) for heading in REPORT_HEADINGS]
    for index, heading in enumerate(REPORT_HEADINGS):
        section_start = heading_positions[index] + 1
        section_end = (
            heading_positions[index + 1] if index + 1 < len(heading_positions) else len(lines)
        )
        if not any(line.strip() for line in lines[section_start:section_end]):
            fail(f"report section is empty: {heading}")

    for table_header, expected_columns in REPORT_TABLES:
        try:
            header_index = lines.index(table_header)
        except ValueError:
            fail(f"report table header is missing: {table_header}")
        separator_index = header_index + 1
        if separator_index >= len(lines) or not lines[separator_index].startswith("|---"):
            fail(f"report table separator is missing: {table_header}")
        if _table_column_count(table_header) != expected_columns:
            fail(f"report table header has the wrong column count: {table_header}")
        if _table_column_count(lines[separator_index]) != expected_columns:
            fail(f"report table separator has the wrong column count: {table_header}")
        data_rows = []
        for line in lines[separator_index + 1 :]:
            if not line.strip() or line.startswith("## "):
                break
            if line.startswith("|"):
                data_rows.append(line)
        if len(data_rows) < 2 or any(
            _table_column_count(row) != expected_columns for row in data_rows
        ):
            fail(f"report table has insufficient or malformed data rows: {table_header}")

    if any(marker in report for marker in UNSAFE_LOCAL_PATH_MARKERS):
        fail("report contains a machine-local absolute path")


def load_rows(path: Path) -> list[dict[str, object]]:
    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != REQUIRED_COLUMNS:
                fail(f"unexpected schema: {reader.fieldnames}")
            raw_rows = list(reader)
    except OSError as exc:
        fail(f"cannot read sample data: {exc}")
    if not raw_rows:
        fail("sample data is empty")

    rows: list[dict[str, object]] = []
    seen_grain: set[tuple[date, str]] = set()
    channels_by_week: dict[date, set[str]] = defaultdict(set)
    for index, raw in enumerate(raw_rows, start=2):
        extra_fields = raw.get(None)
        if extra_fields:
            fail(f"unexpected extra field at CSV row {index}")
        if any(raw.get(column, "").strip() == "" for column in REQUIRED_COLUMNS):
            fail(f"null or blank value at CSV row {index}")
        try:
            week = date.fromisoformat(raw["week_start"])
            sessions = int(raw["sessions"])
            signups = int(raw["signups"])
            paid = int(raw["paid_conversions"])
        except (TypeError, ValueError) as exc:
            fail(f"invalid typed value at CSV row {index}: {exc}")
        channel = raw["channel"].strip()
        if week.weekday() != 0:
            fail(f"week_start must be Monday at CSV row {index}")
        if channel not in ALLOWED_CHANNELS:
            fail(f"unexpected channel at CSV row {index}: {channel}")
        if sessions <= 0 or not 0 <= paid <= signups <= sessions:
            fail(f"invalid funnel ordering or zero sessions at CSV row {index}")
        grain = (week, channel)
        if grain in seen_grain:
            fail(f"duplicate week/channel grain at CSV row {index}")
        seen_grain.add(grain)
        channels_by_week[week].add(channel)
        rows.append(
            {
                "week": week,
                "channel": channel,
                "sessions": sessions,
                "signups": signups,
                "paid": paid,
            }
        )

    incomplete_weeks = [
        week for week, channels in channels_by_week.items() if channels != ALLOWED_CHANNELS
    ]
    if incomplete_weeks:
        fail(f"incomplete channel coverage: {incomplete_weeks}")
    weeks = sorted(channels_by_week)
    missing_periods = [
        (prior, current)
        for prior, current in zip(weeks, weeks[1:])
        if current - prior != timedelta(days=7)
    ]
    if missing_periods:
        fail(f"weekly periods are not consecutive: {missing_periods}")
    freshness_days = (SNAPSHOT_DATE - max(channels_by_week)).days
    if not 0 <= freshness_days <= 7:
        fail(f"sample freshness is outside the declared weekly window: {freshness_days} days")
    return rows


def pct(value: Decimal) -> str:
    return f"{value * 100:.2f}%"


def pp(value: Decimal) -> str:
    return f"{value * 100:+.2f} pp"


def aggregate(
    rows: list[dict[str, object]],
) -> tuple[dict[date, dict[str, int]], dict[date, dict[str, dict[str, int]]]]:
    weekly: dict[date, dict[str, int]] = defaultdict(lambda: {"sessions": 0, "paid": 0})
    by_channel: dict[date, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: {"sessions": 0, "paid": 0})
    )
    for row in rows:
        week = row["week"]
        channel = row["channel"]
        sessions = row["sessions"]
        paid = row["paid"]
        assert isinstance(week, date)
        assert isinstance(channel, str)
        assert isinstance(sessions, int)
        assert isinstance(paid, int)
        weekly[week]["sessions"] += sessions
        weekly[week]["paid"] += paid
        by_channel[week][channel]["sessions"] += sessions
        by_channel[week][channel]["paid"] += paid
    return dict(weekly), {week: dict(values) for week, values in by_channel.items()}


def directional_driver(
    channel_metrics: dict[str, tuple[Decimal, Decimal, Decimal]], total_delta: Decimal
) -> str | None:
    aligned = [
        channel
        for channel, (_, _, delta) in channel_metrics.items()
        if delta != 0 and delta * total_delta > 0
    ]
    if not aligned:
        return None
    return max(sorted(aligned), key=lambda channel: abs(channel_metrics[channel][2]))


def decomposition_share_line(total_delta: Decimal, within_effect: Decimal) -> str:
    if total_delta == 0:
        return "- Within-channel share of aggregate change: `not applicable (aggregate rate unchanged)`"
    ratio = within_effect / total_delta
    direction = "drop" if total_delta < 0 else "increase"
    if ratio >= 0:
        return (
            f"- Share of the observed {direction} associated with the within-channel rate "
            f"effect: `{ratio * 100:.2f}%`"
        )
    return (
        f"- Within-channel rate effect relative to the observed {direction}: "
        f"`{ratio * 100:.2f}% (offsetting)`"
    )


def narrative(
    channel_metrics: dict[str, tuple[Decimal, Decimal, Decimal]],
    total_delta: Decimal,
    mix_effect: Decimal,
    within_effect: Decimal,
) -> tuple[str, str, list[str]]:
    largest = max(sorted(channel_metrics), key=lambda channel: abs(channel_metrics[channel][2]))
    largest_delta = channel_metrics[largest][2]

    if total_delta == 0:
        if all(metrics[2] == 0 for metrics in channel_metrics.values()):
            observation = "All channel rates remained unchanged."
        elif mix_effect != 0 or within_effect != 0:
            observation = (
                "The aggregate rate was unchanged because the channel-mix effect "
                f"({pp(mix_effect)}) offset the within-channel rate effect "
                f"({pp(within_effect)}); the largest absolute channel-rate movement was "
                f"in the {largest} segment ({pp(largest_delta)})."
            )
        else:
            observation = (
                "The aggregate rate was unchanged because weighted channel-rate movements "
                f"offset one another; the largest absolute movement was in the {largest} "
                f"segment ({pp(largest_delta)})."
            )
        attribution = (
            "The aggregate rate was unchanged, so a share-of-change attribution is not "
            "applicable."
        )
        recommendations = [
            "1. Continue monitoring channel rates and volume mix for material movement.",
            "2. Confirm that tracking definitions and late-arriving events remain stable.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
        return observation, attribution, recommendations

    aggregate_direction = "decline" if total_delta < 0 else "increase"
    visible_state = "deterioration" if total_delta < 0 else "improvement"
    driver = directional_driver(channel_metrics, total_delta)
    stable = [channel for channel in CHANNEL_ORDER if channel_metrics[channel][2] == 0]

    if driver is not None and stable:
        stable_channel = stable[0]
        observation = (
            f"{stable_channel.capitalize()} remained at {pct(channel_metrics[stable_channel][1])}; "
            f"the visible {visible_state} is concentrated in the {driver} segment."
        )
    elif driver is not None:
        movement = "decline" if channel_metrics[driver][2] < 0 else "increase"
        observation = (
            f"The largest channel-rate {movement} aligned with the aggregate "
            f"{aggregate_direction} is in the {driver} segment ({pp(channel_metrics[driver][2])})."
        )
    elif all(metrics[2] == 0 for metrics in channel_metrics.values()):
        observation = (
            f"All channel rates remained unchanged; the aggregate {visible_state} is "
            f"associated with the channel-mix effect ({pp(mix_effect)})."
        )
    else:
        relation = "supported" if mix_effect * total_delta > 0 else "opposed"
        observation = (
            f"The aggregate {visible_state} occurred while channel-rate movements did not "
            f"move in the same direction; the channel-mix effect ({pp(mix_effect)}) "
            f"{relation} the net change."
        )

    ratio = within_effect / total_delta
    if ratio > 0:
        attribution = (
            "Under this descriptive decomposition, the within-channel rate effect accounts "
            f"for {ratio * 100:.2f}% of the aggregate {aggregate_direction}."
        )
    elif ratio < 0:
        attribution = (
            f"The within-channel rate effect ({pp(within_effect)}) offsets the aggregate "
            f"{aggregate_direction} by an amount equal to {abs(ratio) * 100:.2f}% of the "
            "observed change."
        )
    else:
        attribution = (
            f"The within-channel rate effect is zero; the aggregate {aggregate_direction} "
            "is associated with the channel-mix effect."
        )

    action = "decline" if total_delta < 0 else "improvement"
    if driver == "ads":
        recommendations = [
            f"1. Validate ads tracking completeness and late-arriving conversions before acting on the {action}.",
            "2. Compare campaign, creative, audience, device, and landing-page mix for the two latest weeks.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
    elif driver is not None:
        recommendations = [
            f"1. Validate {driver} tracking completeness and late-arriving conversions before acting on the {action}.",
            f"2. Compare {driver} source, audience, device, and landing-page mix for the two latest weeks.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
    else:
        recommendations = [
            f"1. Validate tracking completeness and volume-mix definitions before acting on the {action}.",
            "2. Compare channel volume, source composition, device, and landing-page mix for the two latest weeks.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
    return observation, attribution, recommendations


def build_report(source: Path, rows: list[dict[str, object]]) -> str:
    weekly, by_channel = aggregate(rows)
    weeks = sorted(weekly)
    if len(weeks) < 2:
        fail("at least two weekly periods are required")
    prior_week, current_week = weeks[-2], weeks[-1]
    prior = weekly[prior_week]
    current = weekly[current_week]

    prior_rate = Decimal(prior["paid"]) / Decimal(prior["sessions"])
    current_rate = Decimal(current["paid"]) / Decimal(current["sessions"])
    total_delta = current_rate - prior_rate
    relative_delta_text = (
        f"{total_delta / prior_rate * 100:+.2f}% relative"
        if prior_rate != 0
        else "not applicable from a zero baseline"
    )

    channel_metrics: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
    expected_paid = Decimal(0)
    for channel in sorted(ALLOWED_CHANNELS):
        prior_channel = by_channel[prior_week][channel]
        current_channel = by_channel[current_week][channel]
        prior_channel_rate = Decimal(prior_channel["paid"]) / Decimal(prior_channel["sessions"])
        current_channel_rate = Decimal(current_channel["paid"]) / Decimal(current_channel["sessions"])
        channel_metrics[channel] = (
            prior_channel_rate,
            current_channel_rate,
            current_channel_rate - prior_channel_rate,
        )
        expected_paid += Decimal(current_channel["sessions"]) * prior_channel_rate

    counterfactual_rate = expected_paid / Decimal(current["sessions"])
    mix_effect = counterfactual_rate - prior_rate
    within_effect = current_rate - counterfactual_rate
    first_inference, second_inference, recommendations = narrative(
        channel_metrics, total_delta, mix_effect, within_effect
    )
    freshness_days = (SNAPSHOT_DATE - max(weeks)).days

    lines = [
        "# Data analysis pilot report",
        "",
        "> Scope: synthetic sample only. This report does not describe production data or current product performance.",
        "",
        "## Source and quality gate",
        "",
        f"- Source: `{public_source_label(source)}`",
        f"- Snapshot date: `{SNAPSHOT_DATE.isoformat()}`",
        "- Intended grain: one row per `week_start × channel`",
        f"- Rows / periods / channels: `{len(rows)} / {len(weeks)} / {len(ALLOWED_CHANNELS)}`",
        "- Null or blank required values: `0`",
        "- Duplicate grain rows: `0`",
        "- Invalid funnel rows (`paid_conversions <= signups <= sessions`): `0`",
        f"- Freshness lag from latest week to snapshot: `{freshness_days} days`",
        "- Quality gate: **PASS for this synthetic descriptive pilot**",
        "",
        "## Observations",
        "",
        "| Period | Sessions | Paid conversions | Paid conversion rate |",
        "|---|---:|---:|---:|",
        f"| {prior_week.isoformat()} | {prior['sessions']:,} | {prior['paid']:,} | {pct(prior_rate)} |",
        f"| {current_week.isoformat()} | {current['sessions']:,} | {current['paid']:,} | {pct(current_rate)} |",
        "",
        f"The aggregate paid conversion rate changed by **{pp(total_delta)}** ({relative_delta_text}).",
        "",
        "| Channel | Prior rate | Current rate | Change |",
        "|---|---:|---:|---:|",
    ]
    for channel in CHANNEL_ORDER:
        prior_channel_rate, current_channel_rate, channel_delta = channel_metrics[channel]
        lines.append(
            f"| {channel} | {pct(prior_channel_rate)} | {pct(current_channel_rate)} | {pp(channel_delta)} |"
        )
    lines.extend(
        [
            "",
            "## Calculations",
            "",
            f"- Prior aggregate rate: `{prior['paid']} / {prior['sessions']} = {pct(prior_rate)}`",
            f"- Current aggregate rate: `{current['paid']} / {current['sessions']} = {pct(current_rate)}`",
            f"- Current-period counterfactual at prior channel rates: `{pct(counterfactual_rate)}`",
            f"- Channel-mix effect: `{pp(mix_effect)}`",
            f"- Within-channel rate effect: `{pp(within_effect)}`",
            decomposition_share_line(total_delta, within_effect),
            "",
            "## Inferences",
            "",
            f"- {first_inference}",
            f"- {second_inference}",
            "- This decomposition does not establish causality. Campaign mix, attribution, landing-page changes, and late-arriving events were not observed.",
            "",
            "## Recommendations",
            "",
            *recommendations,
            "",
            "## Unknowns",
            "",
            "- Campaign-level composition and spend",
            "- Attribution-window or tracking-definition changes",
            "- Whether recent conversion events are complete",
            "- Production metric definitions and business thresholds",
            "",
            "## Publication boundary",
            "",
            "Only this synthetic aggregate report is approved for repository publication. Raw production rows, identifiers, credentials, connector details, and unpublished business metrics remain outside scope.",
            "",
        ]
    )
    report = "\n".join(lines)
    validate_report_layout(report)
    return report


def run_self_test() -> None:
    zero_delta = {
        "organic": (Decimal("0.08"), Decimal("0.07"), Decimal("-0.01")),
        "ads": (Decimal("0.04"), Decimal("0.03"), Decimal("-0.01")),
    }
    text, _, _ = narrative(zero_delta, Decimal("0"), Decimal("0.01"), Decimal("-0.01"))
    if "channel-mix effect" not in text or "within-channel rate effect" not in text:
        fail("self-test failed: zero-delta decomposition effects were omitted")

    opposite_largest = {
        "organic": (Decimal("0.08"), Decimal("0.13"), Decimal("0.05")),
        "ads": (Decimal("0.04"), Decimal("0.03"), Decimal("-0.01")),
    }
    text, _, _ = narrative(
        opposite_largest, Decimal("-0.005"), Decimal("0"), Decimal("-0.005")
    )
    if "ads segment" not in text or "decline" not in text:
        fail("self-test failed: driver did not follow the aggregate direction")

    ads_improvement = {
        "organic": (Decimal("0.08"), Decimal("0.08"), Decimal("0")),
        "ads": (Decimal("0.04"), Decimal("0.06"), Decimal("0.02")),
    }
    _, _, recommendations = narrative(
        ads_improvement, Decimal("0.01"), Decimal("0"), Decimal("0.01")
    )
    if "improvement" not in recommendations[0] or "decline" in recommendations[0]:
        fail("self-test failed: recommendation direction was inconsistent")

    offsetting = {
        "organic": (Decimal("0.08"), Decimal("0.07"), Decimal("-0.01")),
        "ads": (Decimal("0.04"), Decimal("0.03"), Decimal("-0.01")),
    }
    _, attribution, _ = narrative(
        offsetting, Decimal("0.002"), Decimal("0.012"), Decimal("-0.01")
    )
    calculation = decomposition_share_line(Decimal("0.002"), Decimal("-0.01"))
    if "offsets the aggregate increase" not in attribution or "offsetting" not in calculation:
        fail("self-test failed: offsetting effect lost its sign")

    def expect_rejection(path: Path, expected_message: str) -> None:
        try:
            load_rows(path)
        except SystemExit as exc:
            if expected_message not in str(exc):
                fail(f"self-test failed: unexpected rejection for {path.name}: {exc}")
        else:
            fail(f"self-test failed: invalid fixture was accepted: {path.name}")

    expect_rejection(FIXTURE_ROOT / "missing-week.csv", "weekly periods are not consecutive")
    expect_rejection(FIXTURE_ROOT / "surplus-column.csv", "unexpected extra field")

    fixture_source = Path("tests/fixtures/data-analysis/weekly-metrics.csv")
    fixture_rows = load_rows(REPOSITORY_ROOT / fixture_source)
    fixture_report = build_report(fixture_source, fixture_rows)
    if "tests/fixtures/data-analysis/weekly-metrics.csv" not in fixture_report:
        fail("self-test failed: repository-relative source label was not preserved")
    try:
        validate_report_layout(fixture_report.replace("## Recommendations", "## Broken", 1))
    except SystemExit:
        pass
    else:
        fail("self-test failed: malformed report heading was accepted")
    external_source = REPOSITORY_ROOT.parent / "private-input.csv"
    external_report = build_report(external_source, fixture_rows)
    if "<external source>" not in external_report:
        fail("self-test failed: external source label was not sanitized")

    print("Data analysis narrative self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--expected-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0
    if args.source is None or args.output is None:
        parser.error("--source and --output are required unless --self-test is used")

    run_self_test()
    report = build_report(args.source, load_rows(args.source))
    if args.expected_report:
        try:
            expected = args.expected_report.read_text(encoding="utf-8")
        except OSError as exc:
            fail(f"cannot read expected report: {exc}")
        if report != expected:
            fail("generated report differs from the reviewed pilot report")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print("Data analysis sample pilot: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
