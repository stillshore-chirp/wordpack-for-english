from __future__ import annotations

from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_production_deploy_is_gated_by_a_successful_same_sha_ci_run() -> None:
    workflow = _read(".github/workflows/deploy-production.yml")
    verify = workflow[workflow.index("  verify-target:"): workflow.index("  deploy:")]
    deploy = workflow[workflow.index("  deploy:"):]
    concurrency = workflow[workflow.index("concurrency:"): workflow.index("permissions:")]

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
    assert "CI_WORKFLOW_PATH: .github/workflows/ci.yml" in verify
    assert 'CI_WORKFLOW_ID: "187172373"' in verify
    assert "actions/workflows?per_page=100" in verify
    assert "actions/workflows/${CI_WORKFLOW_ID}/runs" in verify
    assert 'status=completed' in verify
    assert 'conclusion == "success"' in verify
    assert "actions/runs/${run_id}/jobs?per_page=100" in verify
    assert '(.name == "Quality gate"' in verify
    assert 'verify_ci_run "${WORKFLOW_RUN_ID}"' in verify
    assert 'verify_ci_run "${candidate_run_id}"' in verify
    assert "environment: production" not in verify
    assert "needs: verify-target" in deploy
    assert "environment: production" in deploy
    assert "ref: ${{ needs.verify-target.outputs.target_sha }}" in deploy
    assert 'checked_out_sha="$(git rev-parse HEAD)"' in deploy
    assert "group: deploy-production-${{ github.workflow }}" in concurrency
    assert "head_sha" not in concurrency
    assert "inputs." not in concurrency
    assert "github.ref" not in concurrency
    assert "cancel-in-progress: false" in concurrency

    deployment_docs = _read("docs/deployment.md")
    assert ".github/workflows/ci.yml" in deployment_docs
    assert "187172373" in deployment_docs
    assert "Quality gate" in deployment_docs


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


def test_production_auth_is_wif_key_free_and_job_scoped() -> None:
    deploy = _read(".github/workflows/deploy-production.yml")
    preflight = _read(".github/workflows/production-deploy-preflight.yml")

    assert "id-token: write" in deploy
    verify_target = deploy[deploy.index("  verify-target:"): deploy.index("  deploy:")]
    assert "id-token: write" not in verify_target
    assert "permissions:\n      contents: read\n      id-token: write" in deploy[deploy.index("  deploy:"):]
    assert "permissions:\n      contents: read\n      id-token: write" in preflight
    assert "GCP_DEPLOY_SERVICE_ACCOUNT: ${{ vars.GCP_DEPLOY_SERVICE_ACCOUNT }}" in deploy
    assert "GCP_PREFLIGHT_SERVICE_ACCOUNT: ${{ vars.GCP_PREFLIGHT_SERVICE_ACCOUNT }}" in preflight
    assert "GCP_DEPLOY_SERVICE_ACCOUNT" not in preflight
    for workflow in (deploy, preflight):
        assert "credentials_json" not in workflow
        assert "GCP_SA_KEY" not in workflow
        assert "workload_identity_provider:" in workflow
        assert "service_account:" in workflow
        assert "cleanup_credentials: true" in workflow

    assert "gha-creds-*.json" in _read(".gitignore")


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
