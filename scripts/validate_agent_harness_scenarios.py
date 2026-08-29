#!/usr/bin/env python3
"""Validate synthetic agent-harness coordination scenarios.

The fixture is deliberately an event log rather than a list of required words.
Validation therefore checks ordering, state transitions, ownership, and the
identity of reusable evidence without invoking an agent, GitHub, or a server.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, NoReturn, Sequence


SCHEMA_VERSION = 1
REQUIRED_SCENARIOS = {
    "timeout-no-repeat",
    "completed-agent",
    "provisional-after-final-review",
    "resource-ownership-cleanup",
    "evidence-reuse",
}
FORBIDDEN_OUTPUT_KEYS = {
    "final_output",
    "full_output",
    "long_final_output",
    "raw_output",
}
FORBIDDEN_FETCH_TARGETS = {
    "final_output",
    "full_output",
    "long_final_output",
    "raw_output",
    "long_final_result",
}
EVIDENCE_REQUIRED_FIELDS = {
    "scope",
    "acceptance",
    "conclusion",
    "verification_results",
    "unperformed_checks",
    "remaining_risks",
    "snapshot",
    "input_closure",
    "execution_conditions",
}
EVIDENCE_CLOSURE_FIELDS = {"paths", "config", "artifacts"}


class ScenarioValidationError(ValueError):
    """Raised when a synthetic scenario violates a coordination contract."""


def _fail(scenario_id: str, message: str) -> NoReturn:
    raise ScenarioValidationError(f"{scenario_id}: {message}")


def _require(scenario_id: str, condition: bool, message: str) -> None:
    if not condition:
        _fail(scenario_id, message)


def _mapping(scenario_id: str, value: Any, label: str) -> dict[str, Any]:
    _require(scenario_id, isinstance(value, dict), f"{label} must be an object")
    return value


def _events(scenario: Mapping[str, Any]) -> list[dict[str, Any]]:
    scenario_id = str(scenario.get("id", "<missing-id>"))
    value = scenario.get("events")
    _require(scenario_id, isinstance(value, list) and bool(value), "events must be non-empty")
    events: list[dict[str, Any]] = []
    for index, event in enumerate(value):
        _require(scenario_id, isinstance(event, dict), f"event {index} must be an object")
        _require(scenario_id, bool(event.get("type")), f"event {index} is missing type")
        events.append(event)
    return events


def _nonempty_string(scenario_id: str, value: Any, label: str) -> str:
    _require(scenario_id, isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty")
    return value


def _path(value: Any) -> str:
    return str(value).replace("\\", "/").removeprefix("./")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _path_matches(pattern: str, candidate: str) -> bool:
    pattern = _path(pattern)
    candidate = _path(candidate)
    if fnmatch.fnmatchcase(candidate, pattern):
        return True
    if pattern.endswith("/**") and candidate.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    return False


def _paths_intersect(patterns: Iterable[str], changed_path: str) -> bool:
    changed = _path(changed_path)
    return any(
        _path_matches(pattern, changed) or _path_matches(changed, pattern)
        for pattern in patterns
    )


def _validate_timeout_scenario(scenario: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["id"])
    events = _events(scenario)
    generations: dict[str, int] = {}
    blocked: set[str] = set()
    seen_queries: set[tuple[str, str, int]] = set()
    last_backoff: dict[str, float] = {}
    timeout_count = 0
    fresh_signal_count = 0

    for index, event in enumerate(events):
        event_type = str(event["type"])
        state_key = str(event.get("state_key", ""))
        fresh = bool(event.get("new_signal")) or bool(event.get("diagnostic_reason"))
        if fresh:
            _require(scenario_id, bool(state_key), f"event {index} signal is missing state_key")
            generations[state_key] = generations.get(state_key, 0) + 1
            blocked.discard(state_key)
            fresh_signal_count += 1

        if event_type in {"status", "list"}:
            _require(scenario_id, bool(state_key), f"event {index} query is missing state_key")
            _require(
                scenario_id,
                state_key not in blocked,
                f"event {index} repeats status/list for timed-out state without new signal or diagnostic reason",
            )
            query_key = (event_type, state_key, generations.get(state_key, 0))
            _require(scenario_id, query_key not in seen_queries, f"event {index} repeats {event_type} for the same state")
            seen_queries.add(query_key)

        is_timeout = event_type == "timeout" or (
            event_type in {"wait", "re_wait"} and event.get("outcome") == "timeout"
        )
        if not is_timeout:
            continue

        _require(scenario_id, bool(state_key), f"event {index} timeout is missing state_key")
        backoff = event.get("backoff_seconds")
        _require(
            scenario_id,
            isinstance(backoff, (int, float)) and not isinstance(backoff, bool) and backoff > 0,
            f"event {index} timeout needs a positive backoff_seconds",
        )
        previous = last_backoff.get(state_key)
        if previous is not None:
            _require(
                scenario_id,
                float(backoff) > previous,
                f"event {index} timeout backoff must increase for state {state_key}",
            )
            _require(
                scenario_id,
                event.get("operation") == "re_wait" or event_type == "re_wait",
                f"event {index} repeated timeout must use re_wait",
            )
        else:
            _require(
                scenario_id,
                event.get("operation", event_type) in {"wait", "re_wait"},
                f"event {index} timeout must use wait/re_wait",
            )
        last_backoff[state_key] = float(backoff)
        blocked.add(state_key)
        timeout_count += 1

    _require(scenario_id, timeout_count >= 2, "scenario needs consecutive timeout events")
    _require(scenario_id, fresh_signal_count >= 1, "scenario needs a new signal or diagnostic reason after timeout")


def _has_forbidden_output(event: Mapping[str, Any]) -> str | None:
    for key, value in event.items():
        if key in FORBIDDEN_OUTPUT_KEYS and value not in (None, "", [], {}):
            return key
    return None


def _validate_completed_agent_scenario(scenario: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["id"])
    events = _events(scenario)
    completed_index: int | None = None
    read_targets: set[str] = set()

    for index, event in enumerate(events):
        forbidden_key = _has_forbidden_output(event)
        _require(scenario_id, forbidden_key is None, f"event {index} exposes {forbidden_key}")
        event_type = str(event["type"])
        target = str(event.get("target", "")).lower()
        if event_type in {"fetch", "read", "re_fetch", "retrieve"} and target in FORBIDDEN_FETCH_TARGETS:
            if completed_index is not None or event_type in {"re_fetch", "retrieve"}:
                _fail(scenario_id, f"event {index} re-fetches long final output ({target})")
        if event_type == "heartbeat" and event.get("status") == "completed":
            _require(scenario_id, completed_index is None, "completed heartbeat must be unique")
            package = _mapping(scenario_id, event.get("evidence_package"), "completed evidence_package")
            missing = sorted(EVIDENCE_REQUIRED_FIELDS - set(package))
            _require(scenario_id, not missing, f"completed evidence_package missing: {', '.join(missing)}")
            _nonempty_string(scenario_id, event.get("artifact_reference"), "completed artifact_reference")
            for key in package:
                _require(
                    scenario_id,
                    not any(fragment in key.lower() for fragment in ("output", "raw", "full", "log", "history")),
                    f"evidence_package contains unbounded field: {key}",
                )
            completed_index = index
        elif completed_index is not None and event_type in {"fetch", "read", "re_fetch", "retrieve"}:
            _require(
                scenario_id,
                target in {"evidence_package", "artifact_reference", "artifact"},
                f"event {index} reads unsupported completed-agent target: {target}",
            )
            read_targets.add(target)

    _require(scenario_id, completed_index is not None, "missing completed heartbeat")
    _require(scenario_id, "evidence_package" in read_targets, "completed result must use evidence_package")
    _require(
        scenario_id,
        bool(read_targets.intersection({"artifact_reference", "artifact"})),
        "completed result must use artifact_reference",
    )


def _dependency_phase(value: Mapping[str, Any]) -> str:
    return str(value.get("snapshot_phase", value.get("status", ""))).lower()


def _review_is_converged(event: Mapping[str, Any]) -> bool:
    return (
        event.get("type") == "review"
        and str(event.get("status", event.get("state", ""))).lower() == "converged"
    )


def _validate_provisional_final_scenario(scenario: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["id"])
    events = _events(scenario)
    dependencies = scenario.get("depends_on")
    _require(scenario_id, isinstance(dependencies, list) and bool(dependencies), "depends_on must be non-empty")
    dependency_phases: dict[str, str] = {}
    had_nonfinal_dependency = False
    for dependency in dependencies:
        item = _mapping(scenario_id, dependency, "depends_on item")
        dependency_id = _nonempty_string(scenario_id, item.get("id"), "depends_on.id")
        phase = _dependency_phase(item)
        _require(scenario_id, phase in {"implementation", "provisional", "review", "final"}, f"invalid dependency phase: {phase}")
        dependency_phases[dependency_id] = phase
        had_nonfinal_dependency |= phase != "final"

    review_index: int | None = None
    final_index: int | None = None
    provisional_count = 0
    final_evidence: Mapping[str, Any] | None = None

    for index, event in enumerate(events):
        event_type = str(event["type"])
        if event_type == "dependency":
            dependency_id = _nonempty_string(scenario_id, event.get("id"), "dependency.id")
            _require(scenario_id, dependency_id in dependency_phases, f"unknown dependency update: {dependency_id}")
            phase = _dependency_phase(event)
            _require(scenario_id, phase in {"implementation", "provisional", "review", "final"}, f"invalid dependency update phase: {phase}")
            dependency_phases[dependency_id] = phase
        elif _review_is_converged(event):
            _require(scenario_id, review_index is None, "converged review must be unique")
            _nonempty_string(scenario_id, event.get("head"), "review.head")
            _require(scenario_id, event.get("latest_head") == event.get("head"), "review latest_head must equal reviewed head")
            _require(scenario_id, event.get("unresolved_actionable_threads") == 0, "review has unresolved actionable threads")
            _require(scenario_id, str(event.get("mergeability", "")).lower() == "clean", "review mergeability is not clean")
            _require(
                scenario_id,
                all(value == "final" for value in dependency_phases.values()),
                "converged review must follow final dependencies",
            )
            review_index = index
        elif event_type in {"after", "after_evidence", "evidence"} and event.get("kind", "after") == "after":
            phase = str(event.get("snapshot_phase", "")).lower()
            _require(scenario_id, phase in {"provisional", "final"}, f"invalid after snapshot_phase: {phase}")
            if phase == "provisional":
                _require(
                    scenario_id,
                    any(value != "final" for value in dependency_phases.values()),
                    "provisional after evidence requires a non-final dependency",
                )
                provisional_count += 1
                continue
            _require(scenario_id, review_index is not None and review_index < index, "final after evidence needs a prior converged review")
            _require(scenario_id, all(value == "final" for value in dependency_phases.values()), "final after evidence has a non-final dependency")
            _require(scenario_id, event.get("latest_head") == event.get("head"), "final after latest_head must equal evidence head")
            review_event = events[review_index]
            _require(scenario_id, event.get("head") == review_event.get("head"), "final after head differs from converged review head")
            _require(scenario_id, event.get("review_state") == "converged", "final after evidence must record converged review_state")
            _require(scenario_id, event.get("unresolved_actionable_threads") == 0, "final after evidence has unresolved threads")
            _require(scenario_id, str(event.get("mergeability", "")).lower() == "clean", "final after evidence mergeability is not clean")
            _require(scenario_id, final_index is None, "final after evidence must be unique")
            final_index = index
            final_evidence = event

    _require(scenario_id, had_nonfinal_dependency, "scenario must exercise a non-final dependency")
    _require(scenario_id, provisional_count >= 1, "non-final dependency needs provisional after evidence")
    _require(scenario_id, final_evidence is not None and final_index is not None, "scenario needs final after evidence")


def _validate_resource_scenario(scenario: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["id"])
    events = _events(scenario)
    active: dict[str, dict[str, Any]] = {}
    active_ports: dict[int, str] = {}
    ready_resources: set[str] = set()
    acquired_runtime = False
    acquired_port = False
    had_port_claim = False
    released = 0

    for index, event in enumerate(events):
        event_type = str(event["type"])
        if event_type == "acquire":
            resource_id = _nonempty_string(scenario_id, event.get("resource_id"), f"event {index} resource_id")
            owner = _nonempty_string(scenario_id, event.get("owner"), f"event {index} owner")
            resource_type = _nonempty_string(scenario_id, event.get("resource_type"), f"event {index} resource_type")
            _require(scenario_id, resource_type in {"runtime", "port"}, f"event {index} has unsupported resource_type: {resource_type}")
            _require(scenario_id, resource_id not in active, f"event {index} duplicates resource {resource_id}")
            port = event.get("port")
            if resource_type == "runtime":
                _require(scenario_id, isinstance(event.get("pid"), int) and event.get("pid", 0) > 0, f"event {index} runtime needs a positive pid")
                _nonempty_string(scenario_id, event.get("process_group"), f"event {index} process_group")
            _require(scenario_id, port is not None, f"event {index} resource needs a port claim")
            if port is not None:
                _require(scenario_id, isinstance(port, int) and not isinstance(port, bool) and 1 <= port <= 65535, f"event {index} has invalid port")
                _require(scenario_id, port not in active_ports, f"event {index} duplicates port {port}")
                active_ports[port] = resource_id
                had_port_claim = True
            resource = dict(event)
            resource["owner"] = owner
            active[resource_id] = resource
            acquired_runtime |= event.get("resource_type") == "runtime"
            acquired_port |= event.get("resource_type") == "port"
        elif event_type == "ready":
            resource_id = _nonempty_string(scenario_id, event.get("resource_id"), f"event {index} resource_id")
            _require(scenario_id, resource_id in active, f"event {index} readies unknown resource")
            _require(scenario_id, event.get("owner") == active[resource_id]["owner"], f"event {index} readiness owner mismatch")
            _require(scenario_id, event.get("ready") is True, f"event {index} does not confirm readiness")
            ready_resources.add(resource_id)
        elif event_type == "release":
            resource_id = _nonempty_string(scenario_id, event.get("resource_id"), f"event {index} resource_id")
            _require(scenario_id, resource_id in active, f"event {index} releases unknown resource")
            _require(scenario_id, resource_id in ready_resources, f"event {index} releases resource before readiness")
            resource = active[resource_id]
            _require(scenario_id, event.get("owner") == resource["owner"], f"event {index} cleanup owner mismatch")
            _require(scenario_id, event.get("cleanup") == "complete", f"event {index} cleanup is incomplete")
            _require(scenario_id, event.get("process_alive") is False, f"event {index} leaves process alive")
            _require(scenario_id, event.get("port_open") is False, f"event {index} leaves port open")
            port = resource.get("port")
            if port is not None:
                active_ports.pop(port, None)
            active.pop(resource_id)
            ready_resources.discard(resource_id)
            released += 1
        else:
            _fail(scenario_id, f"event {index} has unsupported resource operation: {event_type}")

    _require(scenario_id, acquired_runtime, "scenario needs a runtime resource")
    _require(scenario_id, acquired_port or had_port_claim, "scenario needs a port-bearing resource")
    _require(scenario_id, released >= 1, "scenario needs cleanup release")
    _require(scenario_id, not active, "scenario leaves runtime resource active")
    _require(scenario_id, not active_ports, "scenario leaves port claim active")


def _closure(scenario_id: str, event: Mapping[str, Any]) -> dict[str, list[str]]:
    value = _mapping(scenario_id, event.get("input_closure"), "input_closure")
    missing = sorted(EVIDENCE_CLOSURE_FIELDS - set(value))
    _require(scenario_id, not missing, f"input_closure missing: {', '.join(missing)}")
    result: dict[str, list[str]] = {}
    for field in EVIDENCE_CLOSURE_FIELDS:
        items = value[field]
        _require(scenario_id, isinstance(items, list), f"input_closure.{field} must be a list")
        result[field] = sorted({_path(item) for item in items})
    return result


def _evidence_signature(scenario_id: str, event: Mapping[str, Any]) -> tuple[str, str, str]:
    snapshot = _mapping(scenario_id, event.get("snapshot"), "snapshot")
    _nonempty_string(scenario_id, snapshot.get("base"), "snapshot.base")
    _nonempty_string(scenario_id, snapshot.get("head"), "snapshot.head")
    _nonempty_string(scenario_id, snapshot.get("diff"), "snapshot.diff")
    closure = _closure(scenario_id, event)
    conditions = _mapping(scenario_id, event.get("conditions"), "conditions")
    return _canonical(snapshot), _canonical(closure), _canonical(conditions)


def _validate_evidence_reuse_scenario(scenario: Mapping[str, Any]) -> None:
    scenario_id = str(scenario["id"])
    events = _events(scenario)
    evidence: dict[str, dict[str, Any]] = {}
    stale: set[str] = set()
    saw_reuse = False
    saw_non_intersecting_change = False
    saw_intersecting_invalidation = False

    for index, event in enumerate(events):
        event_type = str(event["type"])
        if event_type == "evidence_success":
            key = _nonempty_string(scenario_id, event.get("key"), f"event {index} key")
            _require(scenario_id, key not in evidence, f"event {index} duplicates evidence key {key}")
            _require(scenario_id, str(event.get("status", "")).lower() in {"passed", "success"}, f"event {index} is not a successful evidence result")
            _nonempty_string(scenario_id, event.get("artifact_reference"), f"event {index} artifact_reference")
            signature = _evidence_signature(scenario_id, event)
            evidence[key] = {"signature": signature, "closure": event["input_closure"], "artifact_reference": event["artifact_reference"]}
        elif event_type == "evidence_reuse":
            source_key = _nonempty_string(scenario_id, event.get("source_key"), f"event {index} source_key")
            _require(scenario_id, source_key in evidence, f"event {index} reuses unknown evidence {source_key}")
            _require(scenario_id, source_key not in stale, f"event {index} reuses invalidated evidence {source_key}")
            signature = _evidence_signature(scenario_id, event)
            _require(scenario_id, signature == evidence[source_key]["signature"], f"event {index} changes snapshot, input closure, or conditions during reuse")
            _require(scenario_id, event.get("artifact_reference") == evidence[source_key]["artifact_reference"], f"event {index} changes artifact_reference during reuse")
            saw_reuse = True
        elif event_type == "path_change":
            changed_path = _nonempty_string(scenario_id, event.get("path"), f"event {index} path")
            intersected = False
            for key, record in evidence.items():
                closure = record["closure"]
                all_patterns = [*closure.get("paths", []), *closure.get("config", []), *closure.get("artifacts", [])]
                if _paths_intersect(all_patterns, changed_path):
                    stale.add(key)
                    intersected = True
            saw_non_intersecting_change |= not intersected
        elif event_type == "evidence_invalidate":
            source_key = _nonempty_string(scenario_id, event.get("source_key"), f"event {index} source_key")
            _require(scenario_id, source_key in stale, f"event {index} invalidates evidence without intersecting change")
            _nonempty_string(scenario_id, event.get("reason"), f"event {index} invalidation reason")
            _nonempty_string(scenario_id, event.get("reacquire_scope"), f"event {index} reacquire_scope")
            stale.remove(source_key)
            saw_intersecting_invalidation = True
        else:
            _fail(scenario_id, f"event {index} has unsupported evidence operation: {event_type}")

    _require(scenario_id, saw_reuse, "scenario needs a successful evidence reuse")
    _require(scenario_id, saw_non_intersecting_change, "scenario needs a non-intersecting path change")
    _require(scenario_id, saw_intersecting_invalidation, "scenario needs an intersecting change and invalidation")
    _require(scenario_id, not stale, "scenario leaves intersecting evidence without invalidation")


def validate_scenario(scenario: Mapping[str, Any]) -> None:
    """Validate one known scenario and raise ``ScenarioValidationError`` on failure."""

    scenario_id = scenario.get("id")
    _require("<document>", isinstance(scenario_id, str) and bool(scenario_id), "scenario id must be non-empty")
    validators = {
        "timeout-no-repeat": _validate_timeout_scenario,
        "completed-agent": _validate_completed_agent_scenario,
        "provisional-after-final-review": _validate_provisional_final_scenario,
        "resource-ownership-cleanup": _validate_resource_scenario,
        "evidence-reuse": _validate_evidence_reuse_scenario,
    }
    validator = validators.get(scenario_id)
    if validator is None:
        _fail(scenario_id, "unknown scenario id")
    validator(scenario)


def validate_document(document: Mapping[str, Any], *, require_all: bool = True) -> None:
    """Validate a fixture document, optionally requiring the complete scenario set."""

    _require("<document>", document.get("kind") == "agent-harness-scenario-fixture", "unexpected fixture kind")
    _require("<document>", document.get("schema_version") == SCHEMA_VERSION, "unsupported schema_version")
    scenarios = document.get("scenarios")
    _require("<document>", isinstance(scenarios, list) and bool(scenarios), "scenarios must be a non-empty list")
    ids: list[str] = []
    for scenario in scenarios:
        item = _mapping("<document>", scenario, "scenario")
        scenario_id = item.get("id")
        _require("<document>", isinstance(scenario_id, str) and bool(scenario_id), "scenario id must be non-empty")
        _require("<document>", scenario_id not in ids, f"duplicate scenario id: {scenario_id}")
        ids.append(scenario_id)
        validate_scenario(item)
    if require_all:
        missing = sorted(REQUIRED_SCENARIOS - set(ids))
        unexpected = sorted(set(ids) - REQUIRED_SCENARIOS)
        _require("<document>", not missing and not unexpected, f"scenario set mismatch (missing={missing}, unexpected={unexpected})")


def load_document(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScenarioValidationError(f"cannot load fixture {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ScenarioValidationError(f"fixture {path} must contain an object")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        document = load_document(args.fixture)
        validate_document(document)
    except ScenarioValidationError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    count = len(document.get("scenarios", []))
    print(f"Agent harness scenario verification: PASS ({count} scenarios)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
