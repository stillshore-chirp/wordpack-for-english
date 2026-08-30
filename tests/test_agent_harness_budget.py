from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.measure_effective_instruction_budget import (
    BudgetMeasurementError,
    build_report,
)


def test_budget_report_sums_explicit_groups_and_marks_estimate(tmp_path: Path) -> None:
    global_path = tmp_path / "budget-global.md"
    nested_path = tmp_path / "budget-nested.md"
    skill_path = tmp_path / "budget-skill.md"
    conditional_path = tmp_path / "budget-hook.md"
    for path, content in (
        (global_path, "global\n"),
        (nested_path, "nested one\nnested two\n"),
        (skill_path, "skill\n"),
        (conditional_path, "hook\n"),
    ):
        path.write_text(content, encoding="utf-8")
    report = build_report(
        revision="head-a",
        apply_paths=["scripts/validate_governance.py"],
        activation_conditions=["agent-harness verifier"],
        paths_by_group={
            "global": [global_path],
            "root": [],
            "nested": [nested_path],
            "activated_skills": [skill_path],
            "conditional_hook_contexts": [conditional_path],
        },
    )
    assert report["groups"]["global"]["lines"] == 1
    assert report["groups"]["nested"]["lines"] == 2
    assert report["totals"]["lines"] == 5
    assert report["totals"]["utf8_bytes"] == 40
    assert report["totals"]["estimated_tokens"] == 12
    assert report["estimate"]["observed_usage"] is None
    assert report["estimate"]["observed_usage_status"] == "not_collected"


def test_budget_serialization_hides_external_absolute_paths(tmp_path: Path) -> None:
    source = tmp_path / "instructions.md"
    source.write_text("four bytes", encoding="utf-8")

    report = build_report(
        revision=str(tmp_path / "revision"),
        apply_paths=[str(tmp_path / "apply.py")],
        activation_conditions=[f"path={tmp_path / 'condition'}"],
        paths_by_group={"global": [source]},
        display_root=Path.cwd(),
    )
    serialized = json.dumps(report, ensure_ascii=False)

    assert str(tmp_path) not in serialized
    assert report["groups"]["global"]["files"][0]["path"] == "<external>/instructions.md"
    assert "<local-path>" in serialized or "<absolute-path>" in serialized


def test_budget_deduplicates_repeated_path_within_group() -> None:
    source = Path("docs/agent-harness.md")

    report = build_report(
        revision="head-a",
        apply_paths=["scripts/validate_governance.py"],
        activation_conditions=[],
        paths_by_group={"root": [source, source]},
    )

    assert len(report["groups"]["root"]["files"]) == 1


def test_budget_rejects_non_utf8_input(tmp_path: Path) -> None:
    source = tmp_path / "binary.md"
    source.write_bytes(b"\xff\xfe")

    with pytest.raises(BudgetMeasurementError, match="not UTF-8"):
        build_report(
            revision="head-a",
            apply_paths=["scripts/validate_governance.py"],
            activation_conditions=[],
            paths_by_group={"root": [source]},
        )
