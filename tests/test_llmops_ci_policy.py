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
    assert "push:" not in deploy
    assert "workflow_run:" in deploy
    assert "- CI" in deploy
    assert "- completed" in deploy
    assert "workflow_dispatch:" in deploy
    assert "target_sha:" in deploy
    assert "github.event.workflow_run.head_sha" in deploy
    assert 'head_sha=${TARGET_SHA}' in deploy
    assert ".head_sha == $target" in deploy
    assert "CI_WORKFLOW_PATH: .github/workflows/ci.yml" in deploy
    assert 'CI_WORKFLOW_ID: "187172373"' in deploy
    assert "actions/runs/${run_id}/jobs?per_page=100" in deploy
    assert "Quality gate" in deploy
    assert '.conclusion == "success"' in deploy
    assert "needs: verify-target" in deploy
    assert "environment: production" in deploy
    assert "llm-live-evaluation" not in deploy
