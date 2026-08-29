#!/usr/bin/env python3
"""Measure a portable, explicit-input estimate of effective instructions.

The command reads only the paths supplied by the caller.  It reports source
size and a transparent token estimate; it does not claim to observe runtime
injection or product token telemetry.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Sequence


SCHEMA_VERSION = 1
GROUPS = (
    "global",
    "root",
    "nested",
    "activated_skills",
    "conditional_hook_contexts",
)
LOCAL_PATH_PATTERN = re.compile(
    r"(?:/Users/|/home/|/private/var/|[A-Za-z]:[\\/])[^\s,;]+"
)
GENERIC_ABSOLUTE_PATH_PATTERN = re.compile(r"(?<![A-Za-z0-9])/(?:[^\s,;]+)")


class BudgetMeasurementError(ValueError):
    """Raised when an explicit budget input cannot be measured safely."""


def _sanitize_text(value: str) -> str:
    """Remove machine-local absolute paths from serialized metadata."""

    sanitized = LOCAL_PATH_PATTERN.sub("<local-path>", value)
    return GENERIC_ABSOLUTE_PATH_PATTERN.sub("<absolute-path>", sanitized)


def _display_path(path: Path, root: Path) -> str:
    """Return a portable path label without exposing the host filesystem."""

    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root.resolve())
    except ValueError:
        return f"<external>/{resolved.name}"
    return relative.as_posix() or "."


def _measure_bytes(raw: bytes) -> dict[str, int]:
    text = raw.decode("utf-8")
    lines = len(text.splitlines())
    # This is intentionally an estimate.  Product tokenizers and runtime
    # injection are outside the scope of a portable source-size check.
    estimated_tokens = math.ceil(len(text) / 4) if text else 0
    return {
        "lines": lines,
        "utf8_bytes": len(raw),
        "estimated_tokens": estimated_tokens,
    }


def _read_measure(path: Path) -> dict[str, int]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise BudgetMeasurementError(f"cannot read input path {path}: {exc}") from exc
    try:
        return _measure_bytes(raw)
    except UnicodeDecodeError as exc:
        raise BudgetMeasurementError(f"input path is not UTF-8: {path}") from exc


def _empty_totals() -> dict[str, int]:
    return {"lines": 0, "utf8_bytes": 0, "estimated_tokens": 0}


def _sum_totals(records: Iterable[dict[str, Any]]) -> dict[str, int]:
    totals = _empty_totals()
    for record in records:
        for field in totals:
            totals[field] += int(record[field])
    return totals


def _group_paths(namespace: argparse.Namespace) -> dict[str, list[Path]]:
    return {
        "global": list(namespace.global_paths),
        "root": list(namespace.root_paths),
        "nested": list(namespace.nested_paths),
        "activated_skills": list(namespace.skill_paths),
        "conditional_hook_contexts": list(namespace.conditional_paths),
    }


def build_report(
    *,
    revision: str,
    apply_paths: Sequence[str],
    activation_conditions: Sequence[str],
    paths_by_group: dict[str, Sequence[Path | str]],
    display_root: Path | None = None,
) -> dict[str, Any]:
    """Build a JSON-ready report from explicit input paths."""

    if not revision.strip():
        raise BudgetMeasurementError("revision must be non-empty")
    if not apply_paths:
        raise BudgetMeasurementError("at least one apply path is required")
    unknown_groups = set(paths_by_group) - set(GROUPS)
    if unknown_groups:
        raise BudgetMeasurementError(f"unknown input groups: {sorted(unknown_groups)}")
    if not any(paths_by_group.get(group) for group in GROUPS):
        raise BudgetMeasurementError("at least one explicit instruction input path is required")

    root = (display_root or Path.cwd()).resolve()
    groups: dict[str, dict[str, Any]] = {}
    grand_records: list[dict[str, Any]] = []
    for group in GROUPS:
        records: list[dict[str, Any]] = []
        seen: set[Path] = set()
        for raw_path in paths_by_group.get(group, ()):
            path = Path(raw_path)
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            measured = _read_measure(path)
            record = {
                "path": _display_path(path, root),
                **measured,
            }
            records.append(record)
            grand_records.append(record)
        groups[group] = {
            "files": records,
            **_sum_totals(records),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "measurement": "effective-instruction-budget",
        "conditions": {
            "revision": _sanitize_text(revision),
            "apply_paths": [_sanitize_text(str(path)) for path in apply_paths],
            "activation_conditions": [_sanitize_text(str(value)) for value in activation_conditions],
        },
        "groups": groups,
        "totals": _sum_totals(grand_records),
        "observed_usage": None,
        "estimate": {
            "token_method": "ceil(unicode_codepoints/4)",
            "observed_usage": None,
            "observed_usage_status": "not_collected",
        },
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True, help="portable revision or snapshot label")
    parser.add_argument("--apply-path", action="append", required=True, help="path covered by this measurement")
    parser.add_argument("--activation-condition", action="append", default=[], help="condition that activates the supplied inputs")
    parser.add_argument("--global", dest="global_paths", action="append", default=[], metavar="PATH")
    parser.add_argument("--root", dest="root_paths", action="append", default=[], metavar="PATH")
    parser.add_argument("--nested", dest="nested_paths", action="append", default=[], metavar="PATH")
    parser.add_argument(
        "--activated-skill",
        "--activated-skills",
        "--skill",
        dest="skill_paths",
        action="append",
        default=[],
        metavar="PATH",
    )
    parser.add_argument(
        "--conditional-hook-context",
        "--conditional-hook-contexts",
        "--conditional",
        dest="conditional_paths",
        action="append",
        default=[],
        metavar="PATH",
    )
    parser.add_argument("--output", type=Path, help="write JSON to this explicit output path instead of stdout")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = build_report(
            revision=args.revision,
            apply_paths=args.apply_path,
            activation_conditions=args.activation_condition,
            paths_by_group=_group_paths(args),
        )
        serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        if args.output:
            try:
                args.output.write_text(serialized, encoding="utf-8")
            except OSError as exc:
                raise BudgetMeasurementError(f"cannot write output: {exc}") from exc
        else:
            sys.stdout.write(serialized)
    except BudgetMeasurementError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
