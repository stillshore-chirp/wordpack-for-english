from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_production_deploy_is_gated_by_a_successful_same_sha_ci_run() -> None:
    workflow = _read(".github/workflows/deploy-production.yml")
    verify = workflow[workflow.index("  verify-target:"): workflow.index("  deploy:")]
    deploy = workflow[workflow.index("  deploy:"):]

    assert "workflow_run:" in workflow
    assert "- CI" in workflow
    assert "- completed" in workflow
    assert "push:" not in workflow
    assert "target_sha:" in workflow
    assert "required: true" in workflow
    assert "github.event.workflow_run.conclusion" in verify
    assert "github.event.workflow_run.event" in verify
    assert "github.event.workflow_run.head_branch" in verify
    assert "gh api" in verify
    assert "actions/runs" in verify
    assert '"CI"' in verify
    assert '"push"' in verify
    assert '"main"' in verify
    assert 'GITHUB_EVENT_NAME}" == "workflow_dispatch"' in verify
    assert 'refs/heads/main' in verify
    assert "environment: production" not in verify
    assert "needs: verify-target" in deploy
    assert "environment: production" in deploy
    assert "ref: ${{ needs.verify-target.outputs.target_sha }}" in deploy
    assert 'checked_out_sha="$(git rev-parse HEAD)"' in deploy


def test_authenticated_preflight_only_uses_trusted_main() -> None:
    workflow = _read(".github/workflows/production-deploy-preflight.yml")

    assert "schedule:" in workflow
    assert "workflow_dispatch:" in workflow
    assert "pull_request:" not in workflow
    assert "pull_request_target:" not in workflow
    assert "static_preflight:" not in workflow
    assert "ref: main" in workflow
    assert "github.event_name == 'schedule'" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    assert 'if [ "$missing" -ne 0 ]; then' in workflow
    assert 'exit 1' in workflow


def test_duplicate_dry_run_workflow_is_removed() -> None:
    assert not Path(".github/workflows/deploy-dry-run.yml").exists()


def test_deploy_script_uses_checked_out_sha_for_image_and_runtime_metadata() -> None:
    script = _read("scripts/deploy_cloud_run.sh")

    assert "IMAGE_TAG_ARG" in script
    assert 'IMAGE_TAG="$CHECKED_OUT_SHA"' in script
    assert 'GIT_SHA="$CHECKED_OUT_SHA"' in script
    assert "IMAGE_TAG_ARG" in script
    assert "GIT_SHA" in script
    assert "--image-tag must equal the checked-out commit SHA" in script
