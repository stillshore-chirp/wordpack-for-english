#!/usr/bin/env python3
"""Run and verify the deterministic sample-data analysis pilot."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import date
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


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


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


def driver_channel(
    channel_metrics: dict[str, tuple[Decimal, Decimal, Decimal]],
) -> str:
    return max(sorted(channel_metrics), key=lambda channel: abs(channel_metrics[channel][2]))


def narrative_lines(
    channel_metrics: dict[str, tuple[Decimal, Decimal, Decimal]],
    total_delta: Decimal,
    within_channel_effect: Decimal,
) -> tuple[str, str, list[str]]:
    driver = driver_channel(channel_metrics)
    driver_delta = channel_metrics[driver][2]
    stable_channels = [
        channel for channel in CHANNEL_ORDER if channel_metrics[channel][2] == 0
    ]

    if total_delta == 0:
        if all(metrics[2] == 0 for metrics in channel_metrics.values()):
            first_inference = "All channel rates remained unchanged."
        else:
            first_inference = (
                "The aggregate rate was unchanged; channel-level movements offset each "
                f"other, with the largest absolute movement in the {driver} segment "
                f"({pp(driver_delta)})."
            )
        share_inference = (
            "The aggregate rate was unchanged, so a share-of-change attribution is not "
            "applicable."
        )
        recommendations = [
            "1. Continue monitoring channel rates and volume mix for material movement.",
            "2. Confirm that tracking definitions and late-arriving events remain stable.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
        return first_inference, share_inference, recommendations

    direction = "deterioration" if total_delta < 0 else "improvement"
    if stable_channels:
        stable = stable_channels[0]
        stable_rate = channel_metrics[stable][1]
        first_inference = (
            f"{stable.capitalize()} remained at {pct(stable_rate)}; the visible "
            f"{direction} is concentrated in the {driver} segment."
        )
    else:
        movement = "decline" if total_delta < 0 else "increase"
        first_inference = (
            f"The largest channel-rate {movement} is in the {driver} segment "
            f"({pp(driver_delta)})."
        )

    driver_share = abs(within_channel_effect / total_delta)
    aggregate_direction = "decline" if total_delta < 0 else "increase"
    share_inference = (
        "Under this descriptive decomposition, the within-channel rate effect accounts "
        f"for {driver_share * 100:.2f}% of the aggregate {aggregate_direction}."
    )
    if driver == "ads":
        recommendations = [
            "1. Validate ads tracking completeness and late-arriving conversions before acting on the decline.",
            "2. Compare campaign, creative, audience, device, and landing-page mix for the two latest weeks.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
    else:
        recommendations = [
            f"1. Validate {driver} tracking completeness and late-arriving conversions before acting on the change.",
            f"2. Compare {driver} source, audience, device, and landing-page mix for the two latest weeks.",
            "3. Use causal language only after a valid experiment or defensible quasi-experimental design is available.",
        ]
    return first_inference, share_inference, recommendations


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
        prior_channel_rate = Decimal(prior_channel["paid"]) / Decimal(
            prior_channel["sessions"]
        )
        current_channel_rate = Decimal(current_channel["paid"]) / Decimal(
            current_channel["sessions"]
        )
        channel_metrics[channel] = (
            prior_channel_rate,
            current_channel_rate,
            current_channel_rate - prior_channel_rate,
        )
        expected_paid += Decimal(current_channel["sessions"]) * prior_channel_rate

    counterfactual_rate = expected_paid / Decimal(current["sessions"])
    mix_effect = counterfactual_rate - prior_rate
    within_channel_effect = current_rate - counterfactual_rate
    first_inference, share_inference, recommendations = narrative_lines(
        channel_metrics, total_delta, within_channel_effect
    )
    freshness_days = (SNAPSHOT_DATE - max(weeks)).days

    if total_delta == 0:
        share_calculation = (
            "- Within-channel share of aggregate change: "
            "`not applicable (aggregate rate unchanged)`"
        )
    else:
        driver_share = abs(within_channel_effect / total_delta)
        aggregate_direction = "drop" if total_delta < 0 else "increase"
        share_calculation = (
            f"- Share of the observed {aggregate_direction} associated with the "
            f"within-channel rate effect: `{driver_share * 100:.2f}%`"
        )

    lines = [
        "# Data analysis pilot report",
        "",
        "> Scope: synthetic sample only. This report does not describe production data or current product performance.",
        "",
        "## Source and quality gate",
        "",
        f"- Source: `{source.as_posix()}`",
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
            f"- Within-channel rate effect: `{pp(within_channel_effect)}`",
            share_calculation,
            "",
            "## Inferences",
            "",
            f"- {first_inference}",
            f"- {share_inference}",
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
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--expected-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

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
