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
        "review-budget",
        "review-budget-exception",
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

    unknown_event = deepcopy(_load("scenarios.json")["scenarios"][0])
    unknown_event["events"][4]["type"] = "bogus"
    with pytest.raises(ScenarioValidationError, match="unknown timeout event"):
        validate_scenario(unknown_event)


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
    unknown_event["events"].insert(3, {"type": "unknown"})
    with pytest.raises(ScenarioValidationError, match="unknown review/after event"):
        validate_scenario(unknown_event)

    unfinal_dependency = deepcopy(_load("scenarios.json")["scenarios"][2])
    unfinal_dependency["events"][2]["snapshot_phase"] = "review"
    with pytest.raises(ScenarioValidationError, match="final dependencies"):
        validate_scenario(unfinal_dependency)


def test_final_after_evidence_is_terminal() -> None:
    for event in (
        {"type": "dependency", "id": "schema-contract", "snapshot_phase": "final"},
        {"type": "review", "status": "converged", "head": "head-b", "latest_head": "head-b", "unresolved_actionable_threads": 0, "mergeability": "clean"},
        {"type": "after", "snapshot_phase": "provisional"},
        {"type": "after", "snapshot_phase": "final"},
    ):
        scenario = deepcopy(_load("scenarios.json")["scenarios"][2])
        scenario["events"].append(event)
        with pytest.raises(ScenarioValidationError, match="terminal final"):
            validate_scenario(scenario)


def test_final_after_rejects_review_stale_state() -> None:
    stale_events = (
        {"type": "review", "status": "changes_requested", "head": "head-b", "latest_head": "head-b"},
        {"type": "review", "status": "commented", "new_actionable_threads": 1},
        {"type": "thread", "status": "open", "actionable": True},
        {"type": "mergeability", "status": "blocked"},
    )
    for stale_event in stale_events:
        scenario = deepcopy(_load("scenarios.json")["scenarios"][2])
        scenario["events"].insert(len(scenario["events"]) - 1, stale_event)
        with pytest.raises(ScenarioValidationError, match="stale"):
            validate_scenario(scenario)

    final_after = deepcopy(_load("scenarios.json")["scenarios"][2])
    final_after["events"][-1]["new_actionable_threads"] = 1
    with pytest.raises(ScenarioValidationError, match="new actionable threads"):
        validate_scenario(final_after)

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


def test_port_resource_requires_its_own_numeric_port() -> None:
    missing_port = deepcopy(_load("scenarios.json")["scenarios"][3])
    port_acquire = next(
        event
        for event in missing_port["events"]
        if event.get("type") == "acquire" and event.get("resource_type") == "port"
    )
    port_acquire.pop("port")
    with pytest.raises(ScenarioValidationError, match="port resource needs a numeric port"):
        validate_scenario(missing_port)

    non_numeric_port = deepcopy(_load("scenarios.json")["scenarios"][3])
    port_acquire = next(
        event
        for event in non_numeric_port["events"]
        if event.get("type") == "acquire" and event.get("resource_type") == "port"
    )
    port_acquire["port"] = "9000"
    with pytest.raises(ScenarioValidationError, match="invalid port"):
        validate_scenario(non_numeric_port)


def test_resource_validator_allows_release_after_failed_readiness() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][3])
    failed_release = next(
        event
        for event in scenario["events"]
        if event.get("type") == "release" and event.get("resource_id") == "failed-runtime"
    )
    failed_release["process_alive"] = True

    with pytest.raises(ScenarioValidationError, match="leaves process alive"):
        validate_scenario(scenario)

    owner_mismatch = deepcopy(_load("scenarios.json")["scenarios"][3])
    failed_release = next(
        event
        for event in owner_mismatch["events"]
        if event.get("type") == "release" and event.get("resource_id") == "failed-runtime"
    )
    failed_release["owner"] = "lane-b"
    with pytest.raises(ScenarioValidationError, match="cleanup owner mismatch"):
        validate_scenario(owner_mismatch)


def test_evidence_reuse_invalidates_only_after_intersecting_change() -> None:
    scenario = deepcopy(_load("scenarios.json")["scenarios"][4])
    cross_snapshot_reuse = next(
        event
        for event in scenario["events"]
        if event.get("type") == "evidence_reuse" and event.get("source_key") == "gate-1"
    )
    invalidation_index = next(
        index for index, event in enumerate(scenario["events"]) if event.get("type") == "evidence_invalidate"
    )
    scenario["events"].insert(invalidation_index + 1, deepcopy(cross_snapshot_reuse))

    with pytest.raises(ScenarioValidationError, match="reuses invalidated evidence"):
        validate_scenario(scenario)

    unchanged_reacquire = deepcopy(_load("scenarios.json")["scenarios"][4])
    gate_one = next(event for event in unchanged_reacquire["events"] if event.get("key") == "gate-1")
    gate_two = next(event for event in unchanged_reacquire["events"] if event.get("key") == "gate-2")
    gate_two["snapshot"] = deepcopy(gate_one["snapshot"])
    gate_two["artifact_reference"] = "artifact:gate-2"
    with pytest.raises(ScenarioValidationError, match="current evidence"):
        validate_scenario(unchanged_reacquire)

    empty_reacquire = deepcopy(_load("scenarios.json")["scenarios"][4])
    gate_two = next(event for event in empty_reacquire["events"] if event.get("key") == "gate-2")
    gate_two["input_closure"] = {"paths": [], "config": [], "artifacts": []}
    with pytest.raises(ScenarioValidationError, match="non-empty input closure"):
        validate_scenario(empty_reacquire)

    unrelated_reacquire = deepcopy(_load("scenarios.json")["scenarios"][4])
    gate_two = next(event for event in unrelated_reacquire["events"] if event.get("key") == "gate-2")
    gate_two["input_closure"]["paths"] = ["docs/unrelated.md"]
    with pytest.raises(ScenarioValidationError, match="cover the changed path"):
        validate_scenario(unrelated_reacquire)


def test_cross_snapshot_reuse_requires_same_base_and_non_intersecting_change() -> None:
    base_changed = deepcopy(_load("scenarios.json")["scenarios"][4])
    cross_snapshot_reuse = next(
        event
        for event in base_changed["events"]
        if event.get("type") == "evidence_reuse" and event.get("source_key") == "gate-1"
    )
    cross_snapshot_reuse["target_snapshot"]["base"] = "base-b"
    with pytest.raises(ScenarioValidationError, match="base snapshot"):
        validate_scenario(base_changed)

    intersecting_change = deepcopy(_load("scenarios.json")["scenarios"][4])
    intersecting_change["events"][1]["path"] = "scripts/verify-agent-harness.sh"
    with pytest.raises(ScenarioValidationError, match="reuses invalidated evidence"):
        validate_scenario(intersecting_change)


def test_evidence_success_binds_reacquisition_to_invalidated_source() -> None:
    missing_binding = deepcopy(_load("scenarios.json")["scenarios"][4])
    gate_two = next(event for event in missing_binding["events"] if event.get("key") == "gate-2")
    gate_two.pop("reacquire_source_key")
    with pytest.raises(ScenarioValidationError, match="reacquire_source_key"):
        validate_scenario(missing_binding)

    wrong_binding = deepcopy(_load("scenarios.json")["scenarios"][4])
    gate_two = next(event for event in wrong_binding["events"] if event.get("key") == "gate-2")
    gate_two["reacquire_source_key"] = "gate-2"
    with pytest.raises(ScenarioValidationError, match="bind reacquisition"):
        validate_scenario(wrong_binding)


def _scenario(name: str) -> dict[str, object]:
    return deepcopy(next(item for item in _load("scenarios.json")["scenarios"] if item["id"] == name))


def test_review_budget_tracks_p2_and_allows_one_terminal_full_gate() -> None:
    scenario = _scenario("review-budget")
    validate_scenario(scenario)

    review = next(event for event in scenario["events"] if event.get("type") == "review")
    assert review["decision_record"]["action"] == "track"
    assert review["decision_record"]["follow_up_reference"]


def test_review_budget_rejects_p2_fix_and_extra_round() -> None:
    p2_fix = _scenario("review-budget")
    review = next(event for event in p2_fix["events"] if event.get("type") == "review")
    review["decision_record"]["action"] = "fix"
    with pytest.raises(ScenarioValidationError, match="P2-only decision"):
        validate_scenario(p2_fix)

    p2_extra_round = _scenario("review-budget")
    review = next(event for event in p2_extra_round["events"] if event.get("type") == "review")
    review["decision_record"]["review_round"] = 2
    with pytest.raises(ScenarioValidationError, match="focused review round"):
        validate_scenario(p2_extra_round)

    unjustified_round = _scenario("review-budget-exception")
    first_review = unjustified_round["events"][1]
    first_review["status"] = "converged"
    first_review["unresolved_actionable_threads"] = 0
    first_review["mergeability"] = "clean"
    first_review["decision_record"] = {
        "review_round": 1,
        "highest_severity": "none",
        "action": "pass",
        "exception_reason": None,
        "invalidated_evidence": [],
        "follow_up_reference": None,
    }
    unjustified_round["events"][2].pop("reacquire_source_key")
    with pytest.raises(ScenarioValidationError, match="second comprehensive review"):
        validate_scenario(unjustified_round)


def test_review_budget_requires_concrete_exception_for_round_three() -> None:
    base = _scenario("review-budget-exception")
    focused_index = next(index for index, event in enumerate(base["events"]) if event.get("scope") == "focused")
    round_three = deepcopy(base["events"][3])
    round_three["decision_record"]["review_round"] = 3
    round_three["decision_record"]["highest_severity"] = "P1"
    round_three["decision_record"]["action"] = "fix"
    round_three["decision_record"]["invalidated_evidence"] = ["review-gate-round-2"]
    round_three["decision_record"]["follow_up_reference"] = "review:628/round-3-fix"
    base["events"].insert(focused_index, round_three)

    with pytest.raises(ScenarioValidationError, match=r"round 3\+"):
        validate_scenario(base)

    abstract_gap = deepcopy(base)
    abstract_gap["events"][focused_index]["decision_record"]["exception_reason"] = {
        "category": "evidence_gap",
        "target_gate": "agent-harness-final",
        "detail": "more evidence would be useful",
        "impact_if_unfixed": "review confidence is lower",
    }
    with pytest.raises(ScenarioValidationError, match="abstract evidence gap"):
        validate_scenario(abstract_gap)

    hard_risk = deepcopy(base)
    hard_risk["events"][focused_index]["decision_record"]["exception_reason"] = {
        "category": "security",
        "target_gate": "agent-harness-final",
        "detail": "synthetic security finding remains actionable",
        "impact_if_unfixed": "the required safety gate could be bypassed",
    }
    gate_three = deepcopy(hard_risk["events"][2])
    gate_three["key"] = "review-gate-round-3"
    gate_three["conditions"]["revision"] = "hard-risk"
    gate_three["reacquire_source_key"] = "review-gate-round-2"
    gate_three["artifact_reference"] = "artifact:review-gate-round-3"
    hard_risk["events"].insert(focused_index + 1, gate_three)
    hard_risk_focused = next(event for event in hard_risk["events"] if event.get("scope") == "focused")
    hard_risk_focused["decision_record"]["review_round"] = 3
    hard_risk_reuse = next(event for event in hard_risk["events"] if event.get("type") == "evidence_reuse")
    hard_risk_reuse["source_key"] = "review-gate-round-3"
    hard_risk_reuse["conditions"]["revision"] = "hard-risk"
    hard_risk_reuse["artifact_reference"] = "artifact:review-gate-round-3"
    validate_scenario(hard_risk)


def test_review_budget_rejects_nonconverged_review_and_gate_reruns() -> None:
    nonconverged = _scenario("review-budget")
    review = next(event for event in nonconverged["events"] if event.get("type") == "review")
    review["status"] = "changes_requested"
    with pytest.raises(ScenarioValidationError, match="focused review must converge"):
        validate_scenario(nonconverged)

    underreported_thread = _scenario("review-budget")
    underreported_thread["events"].insert(1, {"type": "thread", "actionable": True})
    with pytest.raises(ScenarioValidationError, match="underreports actionable threads"):
        validate_scenario(underreported_thread)

    early_gate = _scenario("review-budget")
    gate = deepcopy(next(event for event in early_gate["events"] if event.get("type") == "full_gate"))
    early_gate["events"].insert(1, gate)
    with pytest.raises(ScenarioValidationError, match="requires focused review terminal"):
        validate_scenario(early_gate)

    duplicate_gate = _scenario("review-budget")
    gate = deepcopy(next(event for event in duplicate_gate["events"] if event.get("type") == "full_gate"))
    gate["gate"] = "agent-harness-final-retry"
    duplicate_gate["events"].append(gate)
    with pytest.raises(ScenarioValidationError, match="same closure and conditions"):
        validate_scenario(duplicate_gate)


def test_review_budget_requires_exact_decision_record_and_known_events() -> None:
    missing_field = _scenario("review-budget")
    review = next(event for event in missing_field["events"] if event.get("type") == "review")
    review["decision_record"].pop("follow_up_reference")
    with pytest.raises(ScenarioValidationError, match="exactly the six"):
        validate_scenario(missing_field)

    unknown_event = _scenario("review-budget")
    unknown_event["events"].append({"type": "bogus"})
    with pytest.raises(ScenarioValidationError, match="unknown review-budget event"):
        validate_scenario(unknown_event)


def test_review_budget_decision_invalidation_is_immediately_stateful() -> None:
    reuse_after_decision = _scenario("review-budget-exception")
    reuse_after_decision["events"].insert(
        2,
        {
            "type": "evidence_reuse",
            "source_key": "review-gate-round-1",
            "gate": "agent-harness-review-input",
            "input_closure": {
                "paths": ["scripts/verify-agent-harness.sh"],
                "config": ["requirements-agent-harness.txt"],
                "artifacts": ["verification-summary"],
            },
            "conditions": {"runtime": "static", "python": "3.14"},
            "artifact_reference": "artifact:review-gate-round-1",
        },
    )
    with pytest.raises(ScenarioValidationError, match="reuses invalidated evidence"):
        validate_scenario(reuse_after_decision)

    double_invalidation = _scenario("review-budget-exception")
    double_invalidation["events"].insert(
        2,
        {
            "type": "evidence_invalidate",
            "source_key": "review-gate-round-1",
            "reason": "duplicate invalidation attempt",
        },
    )
    with pytest.raises(ScenarioValidationError, match="invalidates evidence twice"):
        validate_scenario(double_invalidation)


def test_review_budget_blocks_unsafe_blocked_decisions() -> None:
    p2_blocked = _scenario("review-budget")
    review = next(event for event in p2_blocked["events"] if event.get("type") == "review")
    review["decision_record"]["action"] = "blocked"
    review["terminal"] = False
    with pytest.raises(ScenarioValidationError, match="blocked decision needs P0/P1"):
        validate_scenario(p2_blocked)

    missing_follow_up = _scenario("review-budget")
    review = next(event for event in missing_follow_up["events"] if event.get("type") == "review")
    review["status"] = "blocked"
    review["terminal"] = False
    review["decision_record"].update(
        {
            "highest_severity": "P1",
            "action": "blocked",
            "exception_reason": {
                "category": "p1",
                "target_gate": "agent-harness-final",
                "detail": "synthetic blocker remains",
                "impact_if_unfixed": "the final gate is blocked",
            },
            "invalidated_evidence": ["review-gate-before"],
            "follow_up_reference": None,
        }
    )
    with pytest.raises(ScenarioValidationError, match="blocked decision needs follow_up_reference"):
        validate_scenario(missing_follow_up)

    missing_exception = _scenario("review-budget")
    review = next(event for event in missing_exception["events"] if event.get("type") == "review")
    review["status"] = "blocked"
    review["terminal"] = False
    review["decision_record"].update(
        {
            "highest_severity": "P1",
            "action": "blocked",
            "invalidated_evidence": ["review-gate-before"],
            "follow_up_reference": "review:628/blocker",
        }
    )
    with pytest.raises(ScenarioValidationError, match="blocked decision needs exception_reason"):
        validate_scenario(missing_exception)

    missing_invalidation = _scenario("review-budget")
    review = next(event for event in missing_invalidation["events"] if event.get("type") == "review")
    review["status"] = "blocked"
    review["terminal"] = False
    review["decision_record"].update(
        {
            "highest_severity": "P1",
            "action": "blocked",
            "exception_reason": {
                "category": "p1",
                "target_gate": "agent-harness-final",
                "detail": "synthetic blocker remains",
                "impact_if_unfixed": "the final gate is blocked",
            },
            "invalidated_evidence": [],
            "follow_up_reference": "review:628/blocker",
        }
    )
    with pytest.raises(ScenarioValidationError, match="exception_reason needs invalidated_evidence"):
        validate_scenario(missing_invalidation)


def test_review_budget_requires_explicit_hard_risk_severity_and_normalizes_category() -> None:
    missing_severity = _scenario("review-budget-exception")
    review = missing_severity["events"][1]
    review["decision_record"]["highest_severity"] = "none"
    review["decision_record"]["exception_reason"] = {
        "category": "security",
        "target_gate": "agent-harness-final",
        "detail": "synthetic security finding",
        "impact_if_unfixed": "the safety gate could be bypassed",
    }
    with pytest.raises(ScenarioValidationError, match="explicit highest_severity"):
        validate_scenario(missing_severity)

    trailing_gap = _scenario("review-budget-exception")
    review = trailing_gap["events"][1]
    review["decision_record"]["exception_reason"] = {
        "category": "evidence gap ",
        "target_gate": "agent-harness-final",
        "detail": "more evidence would be useful",
        "impact_if_unfixed": "review confidence is lower",
    }
    with pytest.raises(ScenarioValidationError, match="abstract evidence gap"):
        validate_scenario(trailing_gap)


def test_review_budget_rejects_unbounded_or_private_event_strings() -> None:
    local_absolute = "/" + "tmp/local-follow-up"
    secret_like = "token" + "=" + "sk" + "-" + "live-123456789"
    mutations = (
        ("issue:628\nfollow-up", "contains a newline"),
        (local_absolute, "local absolute path"),
        (secret_like, "secret-like value"),
        ("x" * 257, "exceeds the public string limit"),
    )
    for value, message in mutations:
        scenario = _scenario("review-budget")
        review = next(event for event in scenario["events"] if event.get("type") == "review")
        review["decision_record"]["follow_up_reference"] = value
        with pytest.raises(ScenarioValidationError, match=message):
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
    assert "PASS (7 scenarios)" in positive.stdout
    assert negative.returncode != 0
    assert "ERROR:" in negative.stderr
