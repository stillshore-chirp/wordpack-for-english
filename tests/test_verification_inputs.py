from __future__ import annotations

import json
from pathlib import Path
import subprocess

from scripts.classify_verification_inputs import (
    AGENT_HARNESS_FULL,
    AI_GOVERNANCE_FULL,
    BACKEND_FULL,
    BASE_HEAD_CLASSIFICATION,
    FOCUSED_CONTRACT,
    GATE_INPUTS,
    LATEST_ACTIONS,
    WORKFLOW_CONTRACT,
    WORKFLOW_YAML_EVIDENCE,
    YAML_PARSE,
    changed_paths,
    classify_paths,
    main,
)


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
    assert plan.invalidated_gates == (WORKFLOW_CONTRACT,)
    assert set(plan.selected_checks) == {
        FOCUSED_CONTRACT,
        YAML_PARSE,
        BASE_HEAD_CLASSIFICATION,
        LATEST_ACTIONS,
    }
    assert plan.retained_evidence == ()


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


def test_subagent_scenario_contract_uses_existing_marker() -> None:
    source = Path("docs/agent-harness.md").read_text(encoding="utf-8")
    block = source.split("<!-- agent-harness:subagent-orchestration:start -->", 1)[1]
    block = block.split("<!-- agent-harness:subagent-orchestration:end -->", 1)[0]
    for term in (
        "subagent-default（subagent-first）",
        "direct-primary exception",
        "specific reason",
        "target paths",
        "full fileやfull logを要求しません",
        "scope shrink → partial result → reassign → primary",
        "first agent failure alone",
        "製品固有のtool、UI、runtime config",
    ):
        assert term in block
    assert "ここへ詳細を複製しません" in Path("AGENTS.md").read_text(encoding="utf-8")
