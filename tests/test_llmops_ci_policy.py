from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_normal_ci_and_deploy_do_not_reference_llmops_secrets_or_live_eval() -> None:
    for path in Path(".github/workflows").glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        assert "scripts/llmops/live_eval.py" not in text, path
        assert "secrets.OPENAI_API_KEY" not in text, path
        assert "secrets.LANGFUSE_PUBLIC_KEY" not in text, path
        assert "secrets.LANGFUSE_SECRET_KEY" not in text, path
    ci = _read(".github/workflows/ci.yml")
    assert "scripts/llmops/offline_report.py" in ci
    assert "continue-on-error: true" in ci


def test_production_deploy_is_ci_authorized_and_does_not_depend_on_evaluation() -> None:
    deploy = _read(".github/workflows/deploy-production.yml")
    ci = _read(".github/workflows/ci.yml")
    assert "push:" not in deploy
    assert "workflow_run:" not in deploy
    assert "workflow_call:" in deploy
    assert "workflow_dispatch:" in deploy
    assert "target_sha:" in deploy
    assert "ci_run_id:" in deploy
    assert "CALLER_SHA" in deploy
    assert "CALLER_RUN_ID" in deploy
    assert "CALLER_WORKFLOW_REF" in deploy
    assert "EXPECTED_CI_WORKFLOW_REF" in deploy
    assert '"push"' in deploy
    assert 'head_sha=${TARGET_SHA}' in deploy
    assert ".head_sha == $target" in deploy
    assert "CI_WORKFLOW_PATH: .github/workflows/ci.yml" in deploy
    assert 'CI_WORKFLOW_ID: "187172373"' in deploy
    assert "actions/runs/${run_id}/jobs?per_page=100" in deploy
    assert "Quality gate" in deploy
    assert '.conclusion == "success"' in deploy
    assert '.status == "in_progress"' in deploy
    assert "uses: ./.github/workflows/deploy-production.yml" in ci
    assert "needs: quality_gate" in ci
    assert "needs.quality_gate.result == 'success'" in ci
    assert "target_sha: ${{ github.sha }}" in ci
    assert "ci_run_id: ${{ github.run_id }}" in ci
    assert "Deploy production" in ci
    assert "needs: verify-target" in deploy
    assert "environment: production" in deploy
    assert "llm-live-evaluation" not in deploy
