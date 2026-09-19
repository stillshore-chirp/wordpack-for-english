from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.classify_verification_inputs import (
    AGENT_HARNESS_FULL,
    AI_GOVERNANCE_FULL,
    BACKEND_FULL,
    BASE_HEAD_CLASSIFICATION,
    FOCUSED_CONTRACT,
    GATE_INPUTS,
    LATEST_ACTIONS,
    OUTPUT_FIELDS,
    REGISTERED_FULL_E2E_SPECS,
    WORKFLOW_CONTRACT,
    WORKFLOW_YAML_EVIDENCE,
    YAML_PARSE,
    changed_paths,
    classify_path,
    classify_paths,
    main,
)


def test_docs_only_is_known_and_does_not_select_runtime_or_ui() -> None:
    plan = classify_paths(["docs/README.md"])

    assert plan.classification_ok is True
    assert plan.categories == ("docs",)
    assert not any(getattr(plan, field) for field in OUTPUT_FIELDS[:-1])
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)


def test_governance_only_is_governance_without_runtime_gates() -> None:
    plan = classify_paths(
        [".agents/skills/example/SKILL.md", "docs/ai-governance/policy.md"]
    )

    assert plan.classification_ok is True
    assert plan.governance is True
    assert plan.backend is False
    assert plan.frontend is False
    assert plan.backend_container is False
    assert plan.deploy_preflight is False
    assert plan.dependency_review is False
    assert plan.playwright_smoke is False
    assert plan.playwright_visual is False
    assert set(plan.categories) == {"governance", "skill"}


def test_backend_runtime_and_tests_keep_container_boundary() -> None:
    runtime = classify_paths(["apps/backend/backend/main.py"])
    test_only = classify_paths(["tests/backend/test_health.py"])

    assert runtime.classification_ok is True
    assert runtime.backend is True
    assert runtime.backend_container is True
    assert runtime.dependency_review is False
    assert runtime.frontend is False
    assert runtime.deploy_preflight is False
    assert runtime.playwright_smoke is False
    assert runtime.playwright_visual is False
    assert runtime.categories == ("backend_runtime",)
    assert test_only.backend is True
    assert test_only.backend_container is False
    assert test_only.dependency_review is False
    assert test_only.categories == ("backend_test",)


def test_frontend_unit_test_selects_frontend_only() -> None:
    plan = classify_paths(["apps/frontend/src/components/Button.test.tsx"])

    assert plan.frontend is True
    assert plan.playwright_smoke is False
    assert plan.playwright_visual is False
    assert plan.categories == ("frontend_test",)


def test_frontend_library_runtime_selects_smoke_only() -> None:
    plan = classify_paths(["apps/frontend/src/lib/date.ts"])

    assert plan.frontend is True
    assert plan.playwright_smoke is True
    assert plan.playwright_visual is False
    assert plan.categories == ("frontend_runtime",)


def test_visual_runtime_and_assets_select_visual_with_runtime_boundary() -> None:
    page = classify_paths(["apps/frontend/src/pages/Home/index.tsx"])
    asset = classify_paths(
        ["apps/frontend/src/shared/styles/tokens.css", "apps/frontend/public/logo.svg"]
    )

    assert page.frontend is True
    assert page.playwright_smoke is True
    assert page.playwright_visual is True
    assert page.categories == ("frontend_visual",)
    assert asset.frontend is True
    assert asset.playwright_smoke is False
    assert asset.playwright_visual is True
    assert asset.categories == ("frontend_visual",)
    assert page.risks == asset.risks == ("visual",)


def test_deploy_container_and_dependency_categories_are_explicit() -> None:
    deploy = classify_paths(["scripts/deploy_cloud_run.sh"])
    container = classify_paths(["Dockerfile.backend"])
    dependency = classify_paths(["requirements.txt"])

    assert deploy.deploy_preflight is True
    assert deploy.workflow_contract is False
    assert deploy.dependency_review is False
    assert deploy.categories == ("deploy",)
    assert container.backend_container is True
    assert container.dependency_review is True
    assert container.backend is False
    assert container.categories == ("container",)
    assert dependency.backend is True
    assert dependency.backend_container is True
    assert dependency.dependency_review is True
    assert dependency.categories == ("dependency",)


def test_backend_artifact_supply_chain_scripts_keep_container_deploy_and_workflow_closure() -> None:
    expected_gates = {"backend_container", "deploy_preflight", "workflow_contract"}
    expected_rules = {
        "scripts/build_backend_artifact.sh": "deploy_artifact_builder",
        "scripts/verify_backend_artifact_attestations.sh": "deploy_artifact_verifier",
    }

    for path, rule_id in expected_rules.items():
        plan = classify_paths([path])

        assert plan.classification_ok is True, path
        assert plan.unknown_path_count == 0, path
        assert set(plan.path_classifications[0].gates) == expected_gates, path
        assert plan.path_classifications[0].rule_id == rule_id, path
        assert plan.path_classifications[0].category == "deploy", path
        assert plan.path_classifications[0].risk == "artifact_supply_chain", path
        assert plan.backend_container is True, path
        assert plan.deploy_preflight is True, path
        assert plan.workflow_contract is True, path
        assert plan.frontend is False, path
        assert plan.playwright_smoke is False, path
        assert plan.playwright_visual is False, path


def test_workflow_contract_input_closure_includes_backend_artifact_supply_chain() -> None:
    closure_paths = set(GATE_INPUTS[WORKFLOW_CONTRACT].paths)

    assert "scripts/build_backend_artifact.sh" in closure_paths
    assert "scripts/verify_backend_artifact_attestations.sh" in closure_paths
    assert "scripts/deploy_cloud_run.sh" in closure_paths
    assert "cloudbuild.backend.yaml" in closure_paths
    assert "tests/test_cloud_build_config.py" in closure_paths
    assert "tests/test_deploy_script_env_guard.py" in closure_paths
    assert "tests/test_deploy_workflow_safety.py" in closure_paths


def test_dependency_scope_distinguishes_root_playwright_and_frontend_packages() -> None:
    root = classify_paths(["package.json"])
    frontend = classify_paths(["apps/frontend/package-lock.json"])

    assert root.playwright_smoke is True
    assert root.playwright_visual is True
    assert root.dependency_review is True
    assert root.frontend is False
    assert frontend.frontend is True
    assert frontend.playwright_smoke is False
    assert frontend.playwright_visual is False
    assert frontend.dependency_review is True


def test_dependency_review_covers_python_graph_dockerfile_and_dependabot_inputs() -> None:
    for path in (
        "requirements-dev.txt",
        "pyproject.toml",
        "poetry.lock",
        "Dockerfile",
        ".github/dependabot.yml",
    ):
        plan = classify_paths([path])
        assert plan.dependency_review is True, path


def test_shared_fixtures_follow_bounded_consumer_domain_map() -> None:
    quiz = classify_paths(["tests/fixtures/quiz_sentence_alignment.json"])
    plugin_eval = classify_paths(
        ["tests/fixtures/plugin-eval/application-security-before/SKILL.md"]
    )

    assert quiz.classification_ok is True
    assert quiz.backend is True
    assert quiz.frontend is True
    assert quiz.backend_container is False
    assert quiz.playwright_smoke is False
    assert quiz.playwright_visual is False
    for fixture in (
        "in-progress-week.csv",
        "missing-week.csv",
        "organic-decline.csv",
        "surplus-column.csv",
        "unchanged-rate.csv",
        "weekly-metrics.csv",
    ):
        data_analysis = classify_paths([f"tests/fixtures/data-analysis/{fixture}"])
        assert data_analysis.classification_ok is True, fixture
        assert data_analysis.governance is True, fixture
        assert data_analysis.backend is False, fixture
        assert data_analysis.frontend is False, fixture
    assert plugin_eval.classification_ok is True
    assert plugin_eval.governance is True
    assert plugin_eval.backend is False
    assert plugin_eval.frontend is False


def test_unknown_fixture_does_not_fall_through_to_gate_free_test_rule() -> None:
    plan = classify_paths(["tests/fixtures/new-consumer/input.json"])

    assert plan.classification_ok is False
    assert plan.unknown_path_count == 1
    assert plan.unknown_paths == ("tests/fixtures/new-consumer/input.json",)
    assert not any(getattr(plan, field) for field in OUTPUT_FIELDS[:-1])


def test_existing_operational_paths_keep_domain_boundaries_without_ui_overtrigger() -> None:
    expected_gates = {
        "Makefile": {"backend_container", "deploy_preflight"},
        ".firebaserc": {"deploy_preflight"},
        "docker-compose.yml": {"backend", "frontend", "backend_container"},
        "apps/frontend/docker-entrypoint.sh": {"frontend"},
        "scripts/check_frontend_architecture_boundaries.mjs": {"frontend"},
        "scripts/security_scan_text.py": {"governance"},
    }

    for path, gates in expected_gates.items():
        plan = classify_paths([path])
        assert plan.classification_ok is True, path
        assert set(plan.path_classifications[0].gates) == gates
        assert plan.playwright_smoke is False, path
        assert plan.playwright_visual is False, path


def test_backend_and_dedicated_contract_tests_keep_high_priority_gates() -> None:
    expected_gates = {
        "tests/test_api.py": {"backend"},
        "tests/conftest.py": {"backend"},
        "tests/firestore_fakes.py": {"backend"},
        "tests/test_public_docs_security.py": {"governance"},
        "tests/test_security_scan_text.py": {"governance"},
        "tests/test_validate_governance.py": {"governance"},
        "tests/test_github_actions_branch_policy.py": {"workflow_contract"},
        "tests/test_scheduled_maintenance_workflow.py": {"workflow_contract"},
        "tests/test_deploy_script_env_guard.py": {"deploy_preflight"},
        "tests/test_deploy_workflow_safety.py": {"deploy_preflight", "workflow_contract"},
    }

    for path, gates in expected_gates.items():
        plan = classify_paths([path])
        assert plan.classification_ok is True, path
        assert set(plan.path_classifications[0].gates) == gates
        assert plan.playwright_smoke is False, path
        assert plan.playwright_visual is False, path


def test_every_tracked_path_is_registered_by_a_domain_rule() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=repo_root
    ).split(b"\0")
    unknown = [
        path.decode("utf-8", errors="surrogateescape")
        for path in tracked
        if path and classify_path(path.decode("utf-8", errors="surrogateescape")) is None
    ]

    assert unknown == []


def test_registered_e2e_specs_map_to_their_gate() -> None:
    smoke = classify_paths(["tests/e2e/auth.spec.ts"])
    visual = classify_paths(["tests/e2e/visual.spec.ts"])
    full = classify_paths(["tests/e2e/errors.spec.ts"])

    assert smoke.playwright_smoke is True
    assert smoke.playwright_visual is False
    assert visual.playwright_smoke is False
    assert visual.playwright_visual is True
    assert full.playwright_smoke is False
    assert full.playwright_visual is False
    assert full.classification_ok is True


def test_registered_full_e2e_spec_selects_only_that_target() -> None:
    plan = classify_paths([REGISTERED_FULL_E2E_SPECS[1]])

    assert plan.classification_ok is True
    assert plan.playwright_targeted is True
    assert plan.playwright_targeted_specs == (REGISTERED_FULL_E2E_SPECS[1],)
    assert plan.playwright_smoke is False
    assert plan.playwright_visual is False
    assert plan.as_json()["playwright_targeted_specs"] == [REGISTERED_FULL_E2E_SPECS[1]]


def test_full_e2e_targets_are_allowlisted_deduplicated_and_combined_with_smoke() -> None:
    plan = classify_paths(
        [
            REGISTERED_FULL_E2E_SPECS[2],
            "tests/e2e/auth.spec.ts",
            REGISTERED_FULL_E2E_SPECS[0],
            REGISTERED_FULL_E2E_SPECS[2],
        ]
    )

    assert plan.classification_ok is True
    assert plan.playwright_smoke is True
    assert plan.playwright_targeted is True
    assert plan.playwright_targeted_specs == (
        REGISTERED_FULL_E2E_SPECS[0],
        REGISTERED_FULL_E2E_SPECS[2],
    )


def test_non_full_paths_do_not_select_targeted_full_e2e_specs() -> None:
    for path in (
        "apps/frontend/src/pages/Home/index.tsx",
        "apps/backend/backend/main.py",
        "docs/README.md",
        ".agents/skills/example/SKILL.md",
    ):
        plan = classify_paths([path])

        assert plan.classification_ok is True, path
        assert plan.playwright_targeted is False, path
        assert plan.playwright_targeted_specs == (), path


def test_unregistered_e2e_is_unknown_and_fails_closed() -> None:
    plan = classify_paths(["tests/e2e/new-flow.spec.ts"])

    assert plan.classification_ok is False
    assert plan.playwright_smoke is False
    assert plan.playwright_visual is False
    assert plan.unknown_path_count == 1
    assert plan.unknown_paths == ("tests/e2e/new-flow.spec.ts",)
    assert plan.fallback_reason
    assert classify_path("tests/e2e/new-flow.spec.ts") is None


def test_new_runtime_root_paths_use_conservative_root_rules() -> None:
    frontend = classify_paths(["apps/frontend/src/new-surface/data.custom"])
    backend = classify_paths(["apps/backend/backend/new-module/data.custom"])

    assert frontend.classification_ok is True
    assert frontend.frontend is True
    assert frontend.playwright_smoke is True
    assert frontend.playwright_visual is False
    assert frontend.unknown_path_count == 0
    assert backend.classification_ok is True
    assert backend.backend is True
    assert backend.unknown_path_count == 0


def test_unknown_paths_are_capped_in_json_but_count_is_preserved() -> None:
    plan = classify_paths([f"new-runtime/path-{index}.toml" for index in range(25)])
    payload = plan.as_json()

    assert plan.classification_ok is False
    assert plan.unknown_path_count == 25
    assert len(payload["unknown_paths"]) == 20
    assert payload["changed_path_count"] == 25


def test_rename_delete_diff_keeps_both_names_with_no_renames(monkeypatch) -> None:
    recorded: list[str] = []

    def fake_run(command: list[str], **_: object) -> object:
        recorded.extend(command)
        return type("Completed", (), {"stdout": b"old/path.py\0new/path.py\0"})()

    monkeypatch.setattr("scripts.classify_verification_inputs.subprocess.run", fake_run)

    assert changed_paths("base", "head") == ["old/path.py", "new/path.py"]
    assert recorded[:2] == ["git", "diff"]
    assert "base...head" in recorded
    assert "--no-renames" in recorded


def test_real_head_to_head_diff_and_cli_succeed() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts/classify_verification_inputs.py"),
            "--base",
            "HEAD",
            "--head",
            "HEAD",
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["changed_path_count"] == 0


def test_diff_failure_is_nonzero_and_emits_fail_fast_contract(tmp_path, monkeypatch, capsys) -> None:
    def fail_diff(_: str, __: str) -> list[str]:
        raise subprocess.CalledProcessError(returncode=128, cmd=["git", "diff"])

    output_path = tmp_path / "github-output"
    monkeypatch.setattr("scripts.classify_verification_inputs.changed_paths", fail_diff)

    assert (
        main(
            [
                "--base",
                "missing",
                "--head",
                "head",
                "--github-output",
                str(output_path),
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["fallback_reason"] == "git diff failed with status 128"
    assert payload["classification_ok"] is False
    assert payload["playwright_smoke"] is False
    assert payload["playwright_visual"] is False
    assert payload["playwright_targeted_specs"] == []
    assert "unknown_paths" in payload
    output = output_path.read_text(encoding="utf-8")
    assert "classification_ok=false" in output
    assert "playwright_smoke=false" in output
    assert "playwright_visual=false" in output
    assert "playwright_targeted=false" in output
    assert "playwright_targeted_specs=[]" in output


def test_full_profile_selects_all_major_gates() -> None:
    plan = classify_paths([], profile="full")

    assert plan.classification_ok is True
    assert all(
        getattr(plan, field) is True
        for field in OUTPUT_FIELDS
        if field not in {"dependency_review", "playwright_targeted"}
    )
    assert plan.dependency_review is False
    assert plan.playwright_targeted is False
    assert plan.playwright_targeted_specs == ()
    assert plan.categories == ("full_profile",)
    assert plan.unknown_path_count == 0


def test_main_full_profile_and_github_output_include_all_boolean_fields(
    tmp_path: Path, capsys
) -> None:
    output_path = tmp_path / "github-output"

    assert main(["--full", "--github-output", str(output_path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert all(
        payload[field] is True
        for field in OUTPUT_FIELDS
        if field not in {"dependency_review", "playwright_targeted"}
    )
    assert payload["dependency_review"] is False
    assert payload["playwright_targeted"] is False
    assert payload["playwright_targeted_specs"] == []
    output_fields = {
        line.split("=", 1)[0]
        for line in output_path.read_text(encoding="utf-8").splitlines()
    }
    assert set(OUTPUT_FIELDS) <= output_fields


def test_gate_inputs_keep_paths_config_artifacts_and_conditions_bound() -> None:
    for closure in GATE_INPUTS.values():
        assert closure.paths
        assert closure.config
        assert closure.artifacts
        assert closure.conditions


def test_classifier_contract_paths_invalidate_workflow_contract() -> None:
    plan = classify_paths(
        [
            "scripts/classify_verification_inputs.py",
            "tests/test_verification_inputs.py",
        ]
    )

    assert plan.workflow_contract is True
    assert plan.invalidated_gates == (WORKFLOW_CONTRACT,)
    assert set(plan.selected_checks) == {
        FOCUSED_CONTRACT,
        BASE_HEAD_CLASSIFICATION,
        LATEST_ACTIONS,
    }
    assert plan.retained_evidence == (WORKFLOW_YAML_EVIDENCE,)


def test_deleted_legacy_classifier_paths_are_known_non_ui_migrations() -> None:
    for path in (
        "scripts/classify_ui_test_changes.py",
        "tests/test_ui_test_change_classifier.py",
    ):
        plan = classify_paths([path])

        assert plan.classification_ok is True
        assert plan.workflow_contract is True
        assert plan.playwright_smoke is False
        assert plan.playwright_visual is False
        assert plan.categories == ("legacy_migration",)


def test_deleted_live_only_paths_are_known_non_runtime_migrations() -> None:
    for path in (
        "evals/cases/live_smoke.json",
        "scripts/llmops/estimate_run.py",
        "scripts/llmops/live_eval.py",
        "tests/fixtures/agent-harness/code-review-graph-policy.json",
        "tests/fixtures/agent-harness/scenarios-invalid.json",
        "tests/fixtures/agent-harness/scenarios.json",
    ):
        plan = classify_paths([path])

        assert plan.classification_ok is True
        assert plan.backend is False
        assert plan.frontend is False
        assert plan.backend_container is False
        assert plan.deploy_preflight is False
        assert plan.governance is False
        assert plan.workflow_contract is False
        assert plan.dependency_review is False
        assert plan.playwright_smoke is False
        assert plan.playwright_visual is False
        assert plan.categories == ("legacy_migration",)
        assert plan.risks == ("non_runtime",)


def test_deleted_visual_workflow_uses_generic_workflow_contract() -> None:
    plan = classify_paths([".github/workflows/playwright-visual.yml"])

    assert plan.classification_ok is True
    assert all(
        getattr(plan, field) is True
        for field in OUTPUT_FIELDS
        if field not in {"dependency_review", "playwright_targeted"}
    )
    assert plan.dependency_review is False
    assert plan.categories == ("workflow",)


def test_ci_workflow_change_selects_all_major_gates() -> None:
    plan = classify_paths([".github/workflows/ci.yml"])

    assert plan.classification_ok is True
    assert all(
        getattr(plan, field) is True
        for field in OUTPUT_FIELDS
        if field not in {"dependency_review", "playwright_targeted"}
    )
    assert plan.dependency_review is False
    assert plan.categories == ("workflow",)


def test_governance_evidence_plan_separates_harness_and_ai_governance() -> None:
    harness = classify_paths([".agents/skills/example/SKILL.md"])
    governance = classify_paths(["docs/ai-governance/policy.md"])

    assert AGENT_HARNESS_FULL in harness.invalidated_gates
    assert AI_GOVERNANCE_FULL in governance.invalidated_gates
    assert harness.governance is True
    assert governance.governance is True


def test_task_state_template_and_test_route_to_governance() -> None:
    plan = classify_paths(
        [
            "docs/ai-governance/templates/task-state.json",
            "tests/test_governance_task_state.py",
            "tests/test_validate_governance.py",
        ]
    )

    assert plan.classification_ok is True
    assert plan.governance is True
    assert plan.backend is False
    assert plan.frontend is False
    assert plan.invalidated_gates == (AI_GOVERNANCE_FULL,)
    assert {item.category for item in plan.path_classifications} == {"governance"}


def test_backend_evidence_plan_keeps_backend_full_separate() -> None:
    plan = classify_paths(["apps/backend/backend/main.py"])

    assert plan.invalidated_gates == (BACKEND_FULL,)


@pytest.mark.parametrize(
    "scenario,paths,invalidated,selected,retained,required_booleans",
    [
        (
            "docs/governance",
            ["docs/ai-governance/policy.md"],
            (AI_GOVERNANCE_FULL,),
            (),
            (WORKFLOW_YAML_EVIDENCE,),
            ("governance",),
        ),
        (
            "ui",
            ["apps/frontend/src/lib/date.ts"],
            (),
            (),
            (WORKFLOW_YAML_EVIDENCE,),
            ("frontend", "playwright_smoke"),
        ),
        (
            "backend/api",
            ["apps/backend/backend/main.py"],
            (BACKEND_FULL,),
            (),
            (WORKFLOW_YAML_EVIDENCE,),
            ("backend",),
        ),
        (
            "workflow",
            [".github/workflows/ci.yml"],
            tuple(sorted({BACKEND_FULL, WORKFLOW_CONTRACT})),
            tuple(sorted({FOCUSED_CONTRACT, YAML_PARSE, BASE_HEAD_CLASSIFICATION, LATEST_ACTIONS})),
            (),
            (
                "backend",
                "frontend",
                "backend_container",
                "deploy_preflight",
                "governance",
                "workflow_contract",
                "playwright_smoke",
                "playwright_visual",
            ),
        ),
    ],
)
def test_representative_gate_plan_keeps_expected_selection_and_retention(
    scenario: str,
    paths: list[str],
    invalidated: tuple[str, ...],
    selected: tuple[str, ...],
    retained: tuple[str, ...],
    required_booleans: tuple[str, ...],
) -> None:
    plan = classify_paths(paths)

    assert plan.classification_ok is True, scenario
    for field in required_booleans:
        assert getattr(plan, field) is True, scenario
    assert plan.invalidated_gates == invalidated, scenario
    assert plan.selected_checks == selected, scenario
    assert plan.retained_evidence == retained, scenario
