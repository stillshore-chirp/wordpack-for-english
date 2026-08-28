#!/usr/bin/env python3
"""Validate the repository's versioned Plugin Eval benchmark config."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_VERIFIER = "python scripts/verify_task_skills.py"
REQUIRED_VERIFIER_COMMANDS = (REQUIRED_VERIFIER,)
REQUIRED_SCENARIO_IDS = {
    "scoped-diff",
    "unavailable-surface",
    "publication-boundary",
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def validate_verifier_commands(commands: Any) -> None:
    if commands != list(REQUIRED_VERIFIER_COMMANDS):
        raise ValueError(
            "benchmark verifier commands must exactly match the reviewed allowlist: "
            + ", ".join(REQUIRED_VERIFIER_COMMANDS)
        )


def validate_config(config: dict[str, Any]) -> None:
    if config.get("kind") != "plugin-eval-benchmark" or config.get("schemaVersion") != 2:
        raise ValueError("benchmark config must use Plugin Eval schemaVersion 2")
    if config.get("targetKind") != "skill" or config.get("targetName") != "application-security":
        raise ValueError("benchmark target must be the application-security Skill")

    runner = config.get("runner", {})
    if runner.get("type") != "codex-cli":
        raise ValueError("benchmark runner must be codex-cli")
    if runner.get("sandbox") != "workspace-write" or runner.get("approvalPolicy") != "never":
        raise ValueError("benchmark sandbox or approval policy changed")

    workspace = config.get("workspace", {})
    if workspace.get("sourcePath") != "." or workspace.get("setupMode") != "copy":
        raise ValueError("benchmark workspace must be a copy of the reviewed repository")

    provisioning = config.get("targetProvisioning", {})
    if provisioning.get("mode") != "isolated-skill-home":
        raise ValueError("benchmark must provision the Skill in an isolated Codex home")

    verifiers = config.get("verifiers", {})
    commands = verifiers.get("commands") if isinstance(verifiers, dict) else None
    validate_verifier_commands(commands)

    scenarios = config.get("scenarios", [])
    if not isinstance(scenarios, list):
        raise ValueError("benchmark scenarios must be a list")
    ids: set[str] = set()
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise ValueError("each benchmark scenario must be an object")
        scenario_id = scenario.get("id")
        if not scenario_id or str(scenario_id) in ids:
            raise ValueError("benchmark scenario ids must be present and unique")
        ids.add(str(scenario_id))
        if not scenario.get("userInput") or not scenario.get("successChecklist"):
            raise ValueError("every benchmark scenario needs input and a success checklist")

    if ids != REQUIRED_SCENARIO_IDS:
        missing = sorted(REQUIRED_SCENARIO_IDS - ids)
        unexpected = sorted(ids - REQUIRED_SCENARIO_IDS)
        details = []
        if missing:
            details.append(f"missing: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected: {', '.join(unexpected)}")
        raise ValueError(
            "benchmark must retain the three reviewed scenario classes ("
            + "; ".join(details)
            + ")"
        )


def run_self_test() -> None:
    validate_verifier_commands(list(REQUIRED_VERIFIER_COMMANDS))
    for commands in (
        [],
        [REQUIRED_VERIFIER, "echo unreviewed"],
        ["echo unreviewed"],
        [REQUIRED_VERIFIER, REQUIRED_VERIFIER],
    ):
        try:
            validate_verifier_commands(commands)
        except ValueError:
            continue
        raise ValueError(
            "self-test failed: verifier allowlist accepted "
            + repr(commands)
        )
    print("Plugin Eval benchmark validator self-test: PASS")


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        run_self_test()
        return 0
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_plugin_eval_benchmark.py <benchmark-config>")
    path = Path(sys.argv[1])
    try:
        validate_config(load_json(path))
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    print("Plugin Eval benchmark config: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
