from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.validate_agent_harness_scenarios import (
    ScenarioValidationError,
    validate_document,
    validate_scenario,
)


FIXTURE_DIR = Path("tests/fixtures/agent-harness")


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_positive_fixture_covers_all_relationship_scenarios() -> None:
    document = _load("scenarios.json")

    validate_document(document)
    assert {item["id"] for item in document["scenarios"]} == {
        "timeout-no-repeat",
        "completed-agent",
        "provisional-after-final-review",
        "resource-ownership-cleanup",
        "evidence-reuse",
    }


def test_negative_fixture_rejects_each_contract_violation() -> None:
    document = _load("scenarios-invalid.json")

    for scenario in document["scenarios"]:
        with pytest.raises(ScenarioValidationError):
            validate_scenario(scenario)


def test_timeout_requires_backoff_and_new_signal_before_requery() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][0])
    scenario["events"][3]["backoff_seconds"] = 10

    with pytest.raises(ScenarioValidationError, match="backoff must increase"):
        validate_scenario(scenario)


def test_completed_agent_only_reuses_evidence_and_artifact() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][1])
    scenario["events"].append({"type": "read", "target": "final_output"})

    with pytest.raises(ScenarioValidationError, match="re-fetches long final output"):
        validate_scenario(scenario)


def test_final_after_requires_converged_review_on_latest_head() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][2])
    scenario["events"][-1]["latest_head"] = "head-c"

    with pytest.raises(ScenarioValidationError, match="latest_head"):
        validate_scenario(scenario)


def test_resource_validator_detects_duplicate_port_and_cleanup_leak() -> None:
    duplicate_port = deepcopy(_load("scenarios.json")["scenarios"][3])
    duplicate_port["events"][2]["port"] = 8000
    with pytest.raises(ScenarioValidationError, match="duplicates port"):
        validate_scenario(duplicate_port)

    cleanup_leak = deepcopy(_load("scenarios.json")["scenarios"][3])
    cleanup_leak["events"][-1]["process_alive"] = True
    with pytest.raises(ScenarioValidationError, match="leaves process alive"):
        validate_scenario(cleanup_leak)


def test_evidence_reuse_invalidates_only_after_intersecting_change() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][4])
    scenario["events"][5] = deepcopy(scenario["events"][3])

    with pytest.raises(ScenarioValidationError, match="reuses invalidated evidence"):
        validate_scenario(scenario)


def test_validator_cli_accepts_positive_and_rejects_negative_fixture() -> None:
    script = Path("scripts/validate_agent_harness_scenarios.py")
    positive = subprocess.run(
        [sys.executable, str(script), str(FIXTURE_DIR / "scenarios.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    negative = subprocess.run(
        [sys.executable, str(script), str(FIXTURE_DIR / "scenarios-invalid.json")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert positive.returncode == 0
    assert "PASS (5 scenarios)" in positive.stdout
    assert negative.returncode != 0
    assert "ERROR:" in negative.stderr
