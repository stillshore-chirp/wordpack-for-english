from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from scripts.classify_verification_inputs import (
    AGENT_HARNESS_FULL,
    AI_GOVERNANCE_FULL,
    BACKEND_FULL,
    BASE_HEAD_CLASSIFICATION,
    FOCUSED_CONTRACT,
    GATE_INPUTS,
    HARNESS_FILES,
    LATEST_ACTIONS,
    WORKFLOW_CONTRACT,
    WORKFLOW_YAML_EVIDENCE,
    YAML_PARSE,
    changed_paths,
    classify_paths,
    main,
)
import scripts.validate_agent_harness_markers as marker_validator
from scripts.validate_agent_harness_scenarios import (
    ScenarioValidationError,
    validate_document,
)


FIXTURE_DIR = Path("tests/fixtures/agent-harness")


def test_classifier_test_and_docs_do_not_invalidate_backend_full() -> None:
    plan = classify_paths(
        [
            "scripts/classify_ui_test_changes.py",
            "tests/test_ui_test_change_classifier.py",
            "docs/testing/index.md",
        ]
    )

    assert BACKEND_FULL not in plan.invalidated_gates
    assert set(plan.invalidated_gates) == {AGENT_HARNESS_FULL, WORKFLOW_CONTRACT}
    assert set(plan.selected_checks) == {
        FOCUSED_CONTRACT,
        BASE_HEAD_CLASSIFICATION,
        LATEST_ACTIONS,
    }
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)


def test_workflow_change_selects_contract_yaml_classifier_and_actions() -> None:
    plan = classify_paths([".github/workflows/agent-harness.yml"])

    assert BACKEND_FULL not in plan.invalidated_gates
    assert plan.invalidated_gates == (AGENT_HARNESS_FULL, WORKFLOW_CONTRACT)
    assert set(plan.selected_checks) == {
        FOCUSED_CONTRACT,
        YAML_PARSE,
        BASE_HEAD_CLASSIFICATION,
        LATEST_ACTIONS,
    }
    assert plan.retained_evidence == ()


def test_canonical_classifier_and_contract_inputs_invalidate_agent_harness() -> None:
    plan = classify_paths(
        [
            "scripts/classify_ui_test_changes.py",
            "scripts/classify_verification_inputs.py",
            "tests/test_github_actions_branch_policy.py",
            "tests/test_ui_test_change_classifier.py",
            "tests/test_verification_inputs.py",
        ]
    )

    assert BACKEND_FULL not in plan.invalidated_gates
    assert plan.invalidated_gates == (AGENT_HARNESS_FULL, WORKFLOW_CONTRACT)
    assert set(plan.selected_checks) == {
        FOCUSED_CONTRACT,
        BASE_HEAD_CLASSIFICATION,
        LATEST_ACTIONS,
    }
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)


def test_code_review_graph_policy_inputs_are_harness_closure_only() -> None:
    paths = [
        "scripts/validate_code_review_graph_policy.py",
        "tests/fixtures/agent-harness/code-review-graph-policy.json",
        "tests/test_code_review_graph_policy.py",
    ]

    plan = classify_paths(paths)

    assert set(paths) <= HARNESS_FILES
    assert set(paths) <= set(GATE_INPUTS[AGENT_HARNESS_FULL].paths)
    assert set(paths) <= set(GATE_INPUTS[AI_GOVERNANCE_FULL].paths)
    assert plan.invalidated_gates == (AGENT_HARNESS_FULL,)
    assert plan.selected_checks == ()
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)
    assert plan.fallback_reason is None
    assert plan.unknown_path_count == 0


def test_workflow_unmodified_review_fix_retains_yaml_evidence() -> None:
    plan = classify_paths(
        [".agents/skills/github-delivery/SKILL.md", "docs/agent-harness.md"]
    )

    assert plan.invalidated_gates == (AGENT_HARNESS_FULL,)
    assert plan.selected_checks == ()
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)


def test_backend_runtime_change_invalidates_backend_full() -> None:
    plan = classify_paths(["apps/backend/backend/main.py"])

    assert plan.invalidated_gates == (BACKEND_FULL,)


def test_containing_governance_gate_omits_agent_harness_gate() -> None:
    plan = classify_paths(["docs/ai-governance/13-maintenance-policy.md", "AGENTS.md"])

    assert plan.invalidated_gates == (AI_GOVERNANCE_FULL,)


def test_governance_script_selects_containing_gate() -> None:
    plan = classify_paths(["scripts/verify-ai-governance.sh"])

    assert plan.invalidated_gates == (AI_GOVERNANCE_FULL,)


def test_github_collaboration_policy_paths_are_governance_closure() -> None:
    declared_paths = {
        ".github/ISSUE_TEMPLATE/**",
        ".github/pull_request_template.md",
        ".github/dependabot.yml",
    }
    assert declared_paths <= set(GATE_INPUTS[AI_GOVERNANCE_FULL].paths)

    for path in (
        ".github/ISSUE_TEMPLATE/review-follow-up.md",
        ".github/pull_request_template.md",
        ".github/dependabot.yml",
    ):
        plan = classify_paths([path])
        assert plan.invalidated_gates == (AI_GOVERNANCE_FULL,)
        assert plan.selected_checks == ()
        assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)
        assert plan.fallback_reason is None
        assert plan.unknown_path_count == 0


def test_unknown_path_uses_reasoned_conservative_fallback() -> None:
    plan = classify_paths(["new-runtime/config.toml"])

    assert set(plan.invalidated_gates) == {
        BACKEND_FULL,
        AI_GOVERNANCE_FULL,
        WORKFLOW_CONTRACT,
    }
    assert plan.fallback_reason
    assert plan.unknown_path_count == 1
    assert plan.retained_evidence == ()


def test_gate_inputs_bind_paths_config_artifacts_and_conditions() -> None:
    for closure in GATE_INPUTS.values():
        assert closure.paths
        assert closure.config
        assert closure.artifacts
        assert closure.conditions


def test_changed_paths_uses_base_head_diff_without_rename_collapse(monkeypatch) -> None:
    recorded: list[str] = []

    def fake_run(command: list[str], **_: object) -> object:
        recorded.extend(command)
        return type("Completed", (), {"stdout": b"old/path.py\0new/path.py\0"})()

    monkeypatch.setattr("scripts.classify_verification_inputs.subprocess.run", fake_run)

    assert changed_paths("base", "head") == ["old/path.py", "new/path.py"]
    assert "base...head" in recorded
    assert "--no-renames" in recorded


def test_changed_paths_captures_raw_git_stderr(monkeypatch) -> None:
    recorded: dict[str, object] = {}

    def fake_run(_: list[str], **kwargs: object) -> object:
        recorded.update(kwargs)
        return type("Completed", (), {"stdout": b""})()

    monkeypatch.setattr("scripts.classify_verification_inputs.subprocess.run", fake_run)

    assert changed_paths("base", "head") == []
    assert recorded["stderr"] is subprocess.PIPE


def test_diff_failure_returns_compact_fallback_without_paths(monkeypatch, capsys) -> None:
    def fail_diff(_: str, __: str) -> list[str]:
        raise subprocess.CalledProcessError(returncode=128, cmd=["git", "diff"])

    monkeypatch.setattr("scripts.classify_verification_inputs.changed_paths", fail_diff)

    assert main(["--base", "missing", "--head", "head"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback_reason"] == "git diff failed with status 128"
    assert "changed_paths" not in payload
    assert "unknown_paths" not in payload


def test_subagent_scenario_contract_uses_stable_marker_ids() -> None:
    document = Path("docs/agent-harness.md")
    comments = {marker_id: marker_validator.marker_comment(marker_id) for marker_id in marker_validator.MARKER_IDS}

    assert marker_validator.canonical_markers(document, comments) == list(marker_validator.MARKER_IDS)


def test_marker_scan_skips_dangling_tracked_symlink_and_keeps_readable_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    readable = tmp_path / "readable.md"
    readable.write_text(marker_validator.marker_comment("01"), encoding="utf-8")
    dangling = tmp_path / "dangling.md"
    dangling.symlink_to(tmp_path / "missing.md")
    comments = {"01": marker_validator.marker_comment("01")}

    monkeypatch.setattr(marker_validator, "tracked_paths", lambda _: [dangling, readable])

    assert marker_validator.marker_counts(tmp_path, comments) == {"01": [readable]}


def _marker_document_root(tmp_path: Path, transform) -> Path:
    root = tmp_path / "marker-root"
    document = root / "docs" / "agent-harness.md"
    document.parent.mkdir(parents=True)
    source = Path("docs/agent-harness.md").read_text(encoding="utf-8")
    document.write_text(transform(source), encoding="utf-8")
    return root


def _run_marker_validator(root: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    document = (root / "docs" / "agent-harness.md").resolve()
    monkeypatch.setattr(marker_validator, "tracked_paths", lambda _: [document])
    monkeypatch.setattr(marker_validator, "check_direct_reachability", lambda _: None)
    monkeypatch.setattr(marker_validator, "check_scenario_coverage", lambda *_: None)
    return marker_validator.main([str(root), str(Path("tests/fixtures/agent-harness/scenarios.json"))])


def _remove_marker(source: str) -> str:
    return source.replace(marker_validator.marker_comment("04"), "", 1)


def _duplicate_marker(source: str) -> str:
    comment = marker_validator.marker_comment("01")
    return source.replace(comment, f"{comment}\n\n{comment}", 1)


def _move_marker_outside_block(source: str) -> str:
    return f"{source}\n{marker_validator.marker_comment('01')}\n"


def _swap_marker_order(source: str) -> str:
    first = marker_validator.marker_comment("01")
    second = marker_validator.marker_comment("02")
    placeholder = "<!-- marker-order-placeholder -->"
    return source.replace(first, placeholder, 1).replace(second, first, 1).replace(placeholder, second, 1)


def _add_deprecated_marker(source: str) -> str:
    return f"{source}\n<!-- {marker_validator.CONTRACT_PREFIX}deprecated -->\n"


@pytest.mark.parametrize(
    ("case", "transform"),
    (
        ("missing", _remove_marker),
        ("duplicate", _duplicate_marker),
        ("outside-block", _move_marker_outside_block),
        ("wrong-order", _swap_marker_order),
        ("deprecated", _add_deprecated_marker),
    ),
)
def test_marker_migration_rejects_invalid_stable_id_layout(
    case: str, transform, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _marker_document_root(tmp_path, transform)

    with pytest.raises(SystemExit):
        _run_marker_validator(root, monkeypatch)


def test_reworded_prose_keeps_stable_ids_and_scenario_behavior(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = Path("docs/agent-harness.md").read_text(encoding="utf-8")
    reworded = source.replace("専門riskを独立したbounded lane", "専門リスクを独立したbounded lane", 1)
    assert reworded != source
    root = _marker_document_root(tmp_path, lambda _: reworded)

    assert _run_marker_validator(root, monkeypatch) == 0
    payload = json.loads((FIXTURE_DIR / "scenarios.json").read_text(encoding="utf-8"))
    validate_document(payload)


def test_stable_ids_require_mapped_scenario_contract(tmp_path: Path) -> None:
    payload = json.loads((FIXTURE_DIR / "scenarios.json").read_text(encoding="utf-8"))
    mapped_ids = set(marker_validator.SCENARIO_COVERAGE.values())
    scenario_ids = {item["id"] for item in payload["scenarios"]}
    assert mapped_ids <= scenario_ids

    broken = deepcopy(payload)
    focused = next(item for item in broken["scenarios"] if item["id"] == "focused-terminal")
    focused["events"] = []
    broken_fixture = tmp_path / "scenarios-missing-behavior.json"
    broken_fixture.write_text(json.dumps(broken), encoding="utf-8")

    with pytest.raises(ScenarioValidationError):
        validate_document(json.loads(broken_fixture.read_text(encoding="utf-8")))


def test_stable_ids_require_each_mapped_scenario_id(tmp_path: Path) -> None:
    payload = json.loads((FIXTURE_DIR / "scenarios.json").read_text(encoding="utf-8"))
    payload["scenarios"] = [
        item for item in payload["scenarios"] if item["id"] != "focused-terminal"
    ]
    fixture = tmp_path / "scenarios-missing-mapping.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SystemExit, match="no scenario contract"):
        marker_validator.check_scenario_coverage(Path.cwd(), fixture)
