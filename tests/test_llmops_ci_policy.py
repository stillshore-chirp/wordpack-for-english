from __future__ import annotations

from pathlib import Path
import re


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_manual_live_workflow_is_dispatch_only_and_bounded() -> None:
    workflow = _read(".github/workflows/llm-live-evaluation.yml")
    on_block = re.search(r"(?ms)^on:\s*\n(.*?)(?=^permissions:)", workflow)
    assert on_block is not None
    assert "workflow_dispatch:" in on_block.group(1)
    for forbidden in ("push:", "pull_request:", "schedule:", "workflow_call:"):
        assert forbidden not in on_block.group(1)
    for required in (
        "RUN_PAID_LIVE_EVALUATION",
        "environment: llm-live-evaluation",
        "hard limit 5",
        "hard limit 30",
        "hard limit 150000",
        "Paid LLM requests: 0",
    ):
        assert required in workflow
    assert "LIVE_EVALUATION_CONFIRM: ${{ inputs.confirm }}" in workflow
    assert '--confirm "${LIVE_EVALUATION_CONFIRM}"' in workflow
    live_run = workflow.split("run: |", 2)[-1]
    assert "${{ inputs.confirm }}" not in live_run


def test_normal_ci_and_deploy_do_not_reference_llmops_secrets_or_live_eval() -> None:
    normal_workflows = [
        path
        for path in Path(".github/workflows").glob("*.yml")
        if path.name != "llm-live-evaluation.yml"
    ]
    for path in normal_workflows:
        text = path.read_text(encoding="utf-8")
        assert "scripts/llmops/live_eval.py" not in text, path
        assert "secrets.OPENAI_API_KEY" not in text, path
        assert "secrets.LANGFUSE_PUBLIC_KEY" not in text, path
        assert "secrets.LANGFUSE_SECRET_KEY" not in text, path
    ci = _read(".github/workflows/ci.yml")
    assert "scripts/llmops/offline_report.py" in ci
    assert "continue-on-error: true" in ci


def test_production_deploy_keeps_existing_trigger_and_does_not_depend_on_evaluation() -> None:
    deploy = _read(".github/workflows/deploy-production.yml")
    assert "branches: [ main ]" in deploy
    assert "workflow_dispatch:" in deploy
    assert "llm-live-evaluation" not in deploy
    assert "needs:" not in deploy
