#!/usr/bin/env python3
"""Validate the pinned Plugin Eval static pilot artifacts."""

from __future__ import annotations

import sys
from pathlib import Path

from validate_plugin_eval_benchmark import load_json, validate_config

REQUIRED_FILES = (
    "before.json",
    "after.json",
    "budget.json",
    "measurement.json",
    "compare.json",
    "generated-benchmark.json",
)


def load(path: Path) -> dict:
    try:
        return load_json(path)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: verify_plugin_eval_outputs.py <artifact-directory> <benchmark-config>"
        )
    artifact_dir = Path(sys.argv[1])
    benchmark_path = Path(sys.argv[2])
    missing = [name for name in REQUIRED_FILES if not (artifact_dir / name).is_file()]
    if missing:
        raise SystemExit(f"ERROR: missing Plugin Eval artifacts: {', '.join(missing)}")

    before = load(artifact_dir / "before.json")
    after = load(artifact_dir / "after.json")
    budget = load(artifact_dir / "budget.json")
    measurement = load(artifact_dir / "measurement.json")
    comparison = load(artifact_dir / "compare.json")
    generated = load(artifact_dir / "generated-benchmark.json")

    before_failures = {
        item.get("id")
        for item in before.get("checks", [])
        if item.get("status") == "fail"
    }
    after_failures = {
        item.get("id")
        for item in after.get("checks", [])
        if item.get("status") == "fail"
    }
    if "broken-relative-links" not in before_failures:
        raise SystemExit("ERROR: baseline fixture did not expose broken-relative-links")
    if after_failures:
        failure_ids = ", ".join(sorted(str(item) for item in after_failures))
        raise SystemExit(f"ERROR: canonical Skill analyzer failures: {failure_ids}")
    after_checks = {item.get("id") for item in after.get("checks", [])}
    if "progressive-disclosure-missing" in after_checks:
        raise SystemExit("ERROR: canonical Skill does not use progressive disclosure")
    support_metrics = [
        item.get("value")
        for item in after.get("metrics", [])
        if item.get("id") == "support_file_count"
    ]
    if not support_metrics or support_metrics[0] < 1:
        raise SystemExit("ERROR: canonical Skill has no deferred support files")
    if comparison.get("kind") != "comparison":
        raise SystemExit("ERROR: compare output has an unexpected kind")
    introduced_failures = comparison.get("introducedFailures", [])
    if introduced_failures:
        raise SystemExit(
            "ERROR: compare output introduced failures: "
            + ", ".join(sorted(str(item) for item in introduced_failures))
        )
    if "broken-relative-links" not in comparison.get("resolvedFailures", []):
        raise SystemExit("ERROR: compare output did not resolve the baseline link failure")
    if budget.get("kind") != "budget-explanation":
        raise SystemExit("ERROR: explain-budget output has an unexpected kind")
    for bucket in ("trigger_cost_tokens", "invoke_cost_tokens", "deferred_cost_tokens"):
        if bucket not in budget.get("budgets", {}):
            raise SystemExit(f"ERROR: budget output is missing {bucket}")
    if measurement.get("kind") != "measurement-plan" or not measurement.get("toolsets"):
        raise SystemExit("ERROR: measurement-plan output is incomplete")
    if generated.get("kind") != "plugin-eval-benchmark" or generated.get("schemaVersion") != 2:
        raise SystemExit("ERROR: generated benchmark schema changed")

    try:
        validate_config(load(benchmark_path))
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print("Plugin Eval static pilot: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
