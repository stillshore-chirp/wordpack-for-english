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


def test_timeout_needs_fresh_signal_for_the_same_state_after_last_timeout() -> None:
    prior_signal = deepcopy(_load("scenarios.json")["scenarios"][0])
    prior_signal["events"].insert(0, {"type": "signal", "state_key": "ci:head-a", "new_signal": True})
    prior_signal["events"][5]["new_signal"] = False
    with pytest.raises(ScenarioValidationError, match="without new signal"):
        validate_scenario(prior_signal)

    other_state = deepcopy(_load("scenarios.json")["scenarios"][0])
    other_state["events"][4]["state_key"] = "ci:other"
    with pytest.raises(ScenarioValidationError, match="without new signal"):
        validate_scenario(other_state)


def test_completed_agent_only_reuses_evidence_and_artifact() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][1])
    scenario["events"].append({"type": "read", "target": "final_output"})

    with pytest.raises(ScenarioValidationError, match="re-fetches long final output"):
        validate_scenario(scenario)


def test_completed_evidence_package_is_bounded_recursively() -> None:
    forbidden_nested_key = deepcopy(_load("scenarios.json")["scenarios"][1])
    forbidden_nested_key["events"][0]["evidence_package"]["details"]["raw_log"] = "secret-free fixture text"
    with pytest.raises(ScenarioValidationError, match="unbounded evidence field"):
        validate_scenario(forbidden_nested_key)

    over_cap = deepcopy(_load("scenarios.json")["scenarios"][1])
    over_cap["output_cap"]["max_bytes"] = 1
    with pytest.raises(ScenarioValidationError, match="exceeds output_cap"):
        validate_scenario(over_cap)

    unknown_event = deepcopy(_load("scenarios.json")["scenarios"][1])
    unknown_event["events"].append({"type": "unknown"})
    with pytest.raises(ScenarioValidationError, match="unknown completed-agent event"):
        validate_scenario(unknown_event)

    sibling_artifact = deepcopy(_load("scenarios.json")["scenarios"][1])
    sibling_artifact["events"][0]["artifact_reference"] = "artifact:agent-a"
    with pytest.raises(ScenarioValidationError, match="inside evidence_package"):
        validate_scenario(sibling_artifact)


def test_final_after_requires_converged_review_on_latest_head() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][2])
    scenario["events"][-1]["latest_head"] = "head-c"

    with pytest.raises(ScenarioValidationError, match="latest_head"):
        validate_scenario(scenario)


def test_provisional_validator_rejects_unknown_event_and_unfinal_dependency() -> None:
    unknown_event = deepcopy(_load("scenarios.json")["scenarios"][2])
    unknown_event["events"].append({"type": "unknown"})
    with pytest.raises(ScenarioValidationError, match="unknown review/after event"):
        validate_scenario(unknown_event)

    unfinal_dependency = deepcopy(_load("scenarios.json")["scenarios"][2])
    unfinal_dependency["events"][2]["snapshot_phase"] = "review"
    with pytest.raises(ScenarioValidationError, match="final dependencies"):
        validate_scenario(unfinal_dependency)


def test_resource_validator_detects_duplicate_port_and_cleanup_leak() -> None:
    duplicate_port = deepcopy(_load("scenarios.json")["scenarios"][3])
    duplicate_port["events"][2]["port"] = 8000
    with pytest.raises(ScenarioValidationError, match="duplicates port"):
        validate_scenario(duplicate_port)

    cleanup_leak = deepcopy(_load("scenarios.json")["scenarios"][3])
    cleanup_leak["events"][-1]["process_alive"] = True
    with pytest.raises(ScenarioValidationError, match="leaves process alive"):
        validate_scenario(cleanup_leak)

    workspace_leak = deepcopy(_load("scenarios.json")["scenarios"][3])
    workspace_release = next(event for event in workspace_leak["events"] if event.get("resource_id") == "frontend-worktree" and event["type"] == "release")
    workspace_release["workspace_exists"] = True
    with pytest.raises(ScenarioValidationError, match="leaves temporary workspace"):
        validate_scenario(workspace_leak)

    owner_mismatch = deepcopy(_load("scenarios.json")["scenarios"][3])
    runtime_release = next(event for event in owner_mismatch["events"] if event.get("resource_id") == "frontend" and event["type"] == "release")
    runtime_release["owner"] = "lane-b"
    with pytest.raises(ScenarioValidationError, match="cleanup owner mismatch"):
        validate_scenario(owner_mismatch)

    duplicate_workspace = deepcopy(_load("scenarios.json")["scenarios"][3])
    duplicate_workspace["events"].insert(
        5,
        {"type": "acquire", "resource_type": "workspace", "resource_id": "other-worktree", "owner": "lane-a", "workspace": "tmp/worktrees/frontend"},
    )
    with pytest.raises(ScenarioValidationError, match="duplicates workspace"):
        validate_scenario(duplicate_workspace)


def test_evidence_reuse_invalidates_only_after_intersecting_change() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][4])
    scenario["events"].insert(6, deepcopy(scenario["events"][1]))

    with pytest.raises(ScenarioValidationError, match="reuses invalidated evidence"):
        validate_scenario(scenario)

    unchanged_reacquire = deepcopy(_load("scenarios.json")["scenarios"][4])
    unchanged_reacquire["events"][6]["snapshot"] = deepcopy(unchanged_reacquire["events"][0]["snapshot"])
    unchanged_reacquire["events"][6]["artifact_reference"] = "artifact:gate-2"
    with pytest.raises(ScenarioValidationError, match="current evidence"):
        validate_scenario(unchanged_reacquire)


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
