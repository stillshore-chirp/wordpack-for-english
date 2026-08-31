from __future__ import annotations

import re
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_production_deploy_is_gated_by_a_successful_same_sha_ci_run() -> None:
    workflow = _read(".github/workflows/deploy-production.yml")
    verify = workflow[workflow.index("  verify-target:"): workflow.index("  verify-deploy-identity:")]
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
    assert "needs:\n      - verify-target\n      - authorize-deploy-cutover" in deploy
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


def test_identity_exchange_cutover_is_manual_only_and_fail_closed() -> None:
    workflow = _read(".github/workflows/deploy-production.yml")
    identity_start = workflow.index("  verify-deploy-identity:")
    guard_start = workflow.index("  authorize-deploy-cutover:")
    deploy_start = workflow.index("  deploy:")
    identity = workflow[identity_start:guard_start]
    guard = workflow[guard_start:deploy_start]
    deploy = workflow[deploy_start:]

    assert "identity_exchange_only:" in workflow
    assert "required: false" in workflow
    assert "default: false" in workflow
    assert "type: boolean" in workflow
    assert "needs: verify-target" in identity
    assert "if: github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main' && inputs.identity_exchange_only == true" in identity
    assert "environment: production" in identity
    assert "permissions:\n      id-token: write" in identity
    assert "token_format: access_token" in identity
    assert "access_token_lifetime: 300s" in identity
    assert "create_credentials_file: false" in identity
    assert "export_environment_variables: false" in identity
    assert "WIF_ACCESS_TOKEN: ${{ steps.gcp-auth.outputs.access_token }}" in identity
    assert '[[ -n "${WIF_ACCESS_TOKEN}" ]] ||' in identity
    assert "Confirm WIF token exchange" in identity
    assert "gcloud auth print-access-token" not in identity
    assert "setup-gcloud" not in identity
    assert 'echo "${WIF_ACCESS_TOKEN}"' not in identity
    assert "GITHUB_STEP_SUMMARY" not in identity
    assert "GITHUB_OUTPUT" not in identity
    assert not re.search(r"actions/checkout@|secrets\.|npm |pip install|make release|promote_cloud_run|deploy_firebase|CLOUD_RUN_ENV_FILE_BASE64|traffic", identity)

    assert "PRODUCTION_DEPLOY_ENABLED: ${{ vars.PRODUCTION_DEPLOY_ENABLED }}" in guard
    assert "if: needs.verify-target.result == 'success' && (github.event_name != 'workflow_dispatch' || inputs.identity_exchange_only != true)" in guard
    assert "${PRODUCTION_DEPLOY_ENABLED:-}" in guard
    assert "!= \"true\"" in guard
    assert "::error::" in guard
    assert "exit 1" in guard
    assert "needs:\n      - verify-target\n      - authorize-deploy-cutover" in deploy
    assert "needs.authorize-deploy-cutover.result == 'success'" in deploy
    assert "inputs.identity_exchange_only != true" in deploy


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
    verify_target = deploy[deploy.index("  verify-target:"): deploy.index("  verify-deploy-identity:")]
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


def test_dedicated_cloud_build_service_account_is_deploy_only() -> None:
    """Cloud Build receives an explicit non-secret SA only on the deploy path."""
    deploy = _read(".github/workflows/deploy-production.yml")
    preflight = _read(".github/workflows/production-deploy-preflight.yml")
    identity = deploy[deploy.index("  verify-deploy-identity:"): deploy.index("  authorize-deploy-cutover:")]
    deploy_job = deploy[deploy.index("  deploy:"):]

    assert "GCP_BUILD_SERVICE_ACCOUNT: ${{ vars.GCP_BUILD_SERVICE_ACCOUNT }}" in deploy_job
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in identity
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in preflight
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in deploy[deploy.index("  verify-target:"): deploy.index("  deploy:")]
    assert 'BUILD_SERVICE_ACCOUNT="${GCP_BUILD_SERVICE_ACCOUNT}"' in deploy_job
    assert "GCP_BUILD_SERVICE_ACCOUNT is not set" in deploy_job
    assert "must be a service-account email in GCP_PROJECT_ID's project" in deploy_job
    assert r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@${GCP_PROJECT_ID}\.iam\.gserviceaccount\.com" in deploy_job

    script = _read("scripts/deploy_cloud_run.sh")
    makefile = _read("Makefile")
    assert '"--service-account=projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}"' in script
    assert '$(if $(BUILD_SERVICE_ACCOUNT),--build-service-account "$(BUILD_SERVICE_ACCOUNT)",)' in makefile


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
