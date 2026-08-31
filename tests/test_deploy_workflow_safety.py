from __future__ import annotations

import re
from pathlib import Path

import yaml


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
    assert "needs:\n      - verify-target\n      - authorize-deploy-cutover\n      - prepare-release-artifacts\n      - build-backend-artifact\n      - attest-backend-artifact" in deploy
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
    assert "needs:\n      - verify-target\n      - authorize-deploy-cutover\n      - prepare-release-artifacts\n      - build-backend-artifact\n      - attest-backend-artifact" in deploy
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
    parsed = yaml.safe_load(deploy)
    assert isinstance(parsed, dict)
    assert parsed["jobs"]["deploy"]["permissions"] == {
        "contents": "read",
        "actions": "read",
        "attestations": "read",
        "id-token": "write",
    }
    assert parsed["jobs"]["build-backend-artifact"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert parsed["jobs"]["attest-backend-artifact"]["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert "id-token: write" not in parsed["jobs"]["prepare-release-artifacts"]["permissions"]
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


def test_dedicated_cloud_build_service_account_is_build_job_only() -> None:
    """Only the authenticated backend-build job owns the builder identity."""
    deploy = _read(".github/workflows/deploy-production.yml")
    preflight = _read(".github/workflows/production-deploy-preflight.yml")
    identity = deploy[deploy.index("  verify-deploy-identity:"): deploy.index("  authorize-deploy-cutover:")]
    build_job = deploy[deploy.index("  build-backend-artifact:"): deploy.index("  attest-backend-artifact:")]
    deploy_job = deploy[deploy.index("  deploy:"):]

    assert "GCP_BUILD_SERVICE_ACCOUNT: ${{ vars.GCP_BUILD_SERVICE_ACCOUNT }}" in build_job
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in identity
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in preflight
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in deploy_job
    assert "must be a service-account email in GCP_PROJECT_ID's project" in build_job
    assert r"^[a-z][a-z0-9-]{4,28}[a-z0-9]@${GCP_PROJECT_ID}\.iam\.gserviceaccount\.com" in build_job
    assert "scripts/build_backend_artifact.sh" in build_job
    assert "--build-service-account" in build_job

    script = _read("scripts/deploy_cloud_run.sh")
    assert "gcloud builds submit" not in script
    helper = _read("scripts/build_backend_artifact.sh")
    assert "gcloud builds submit" in helper
    assert "serviceAccounts/${BUILD_SERVICE_ACCOUNT}" in helper


def test_duplicate_dry_run_workflow_is_removed() -> None:
    assert not Path(".github/workflows/deploy-dry-run.yml").exists()


def test_deploy_script_uses_checked_out_sha_for_image_and_runtime_metadata() -> None:
    script = _read("scripts/deploy_cloud_run.sh")

    assert "--image-uri" in script
    assert "@sha256:" in script
    assert "gcloud builds submit" not in script


def _deploy_job_steps() -> tuple[str, list[dict[str, object]]]:
    path = ".github/workflows/deploy-production.yml"
    workflow = yaml.safe_load(_read(path))
    assert isinstance(workflow, dict)
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    deploy = jobs.get("deploy")
    assert isinstance(deploy, dict)
    steps = deploy.get("steps")
    assert isinstance(steps, list)
    assert all(isinstance(step, dict) for step in steps)
    return _read(path), steps


def _step_text(step: dict[str, object]) -> str:
    return "\n".join(
        str(step.get(key, ""))
        for key in ("name", "uses", "run", "with", "env")
    )


def test_backend_artifact_is_built_once_checked_and_promoted_by_digest() -> None:
    """Build, hand off, attest, verify, and deploy form an isolated chain."""
    workflow, deploy_steps = _deploy_job_steps()
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict)
    jobs = parsed["jobs"]
    prepare = jobs["prepare-release-artifacts"]
    build = jobs["build-backend-artifact"]
    attest = jobs["attest-backend-artifact"]
    deploy = jobs["deploy"]
    prepare_steps = prepare["steps"]
    build_steps = build["steps"]
    attest_steps = attest["steps"]
    rendered_prepare = [_step_text(step) for step in prepare_steps]
    rendered_build = [_step_text(step) for step in build_steps]
    rendered_attest = [_step_text(step) for step in attest_steps]
    rendered_deploy = [_step_text(step) for step in deploy_steps]
    build_helper = _read("scripts/build_backend_artifact.sh")
    verify_helper = _read("scripts/verify_backend_artifact_attestations.sh")
    deploy_script = _read("scripts/deploy_cloud_run.sh")

    assert prepare["needs"] == ["verify-target", "authorize-deploy-cutover"]
    assert build["needs"] == ["verify-target", "authorize-deploy-cutover"]
    assert attest["needs"] == "build-backend-artifact"
    assert deploy["needs"] == [
        "verify-target",
        "authorize-deploy-cutover",
        "prepare-release-artifacts",
        "build-backend-artifact",
        "attest-backend-artifact",
    ]
    assert prepare.get("environment") is None
    assert build["environment"] == "production"
    assert attest.get("environment") is None
    assert deploy["environment"] == "production"

    assert build_helper.count('gcloud builds submit "${BUILD_CONTEXT}"') == 1
    assert "git archive" in build_helper
    assert "mktemp -d" in build_helper
    assert "--show-provenance" in build_helper
    assert "sha256sum" in build_helper
    assert "image_summary.digest" in build_helper
    assert "docker run" in build_helper and "healthz" in build_helper
    assert "@${REGISTRY_DIGEST}" in build_helper
    assert "Install frontend dependencies" in "\n".join(rendered_prepare)
    assert "Build frontend artifact" in "\n".join(rendered_prepare)
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in "\n".join(rendered_prepare)
    assert "scripts/build_backend_artifact.sh" in "\n".join(rendered_build)
    assert "npm " not in "\n".join(rendered_build)
    assert "pip " not in "\n".join(rendered_build)
    assert "actions/attest@" not in "\n".join(rendered_build)
    assert "docker save" in "\n".join(rendered_build)
    assert "zstd" in "\n".join(rendered_build)
    assert "retention-days" in "\n".join(rendered_prepare)
    assert "retention-days" in "\n".join(rendered_build)
    assert "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6" in "\n".join(rendered_attest)
    assert sum("actions/attest@" in text for text in rendered_attest) == 2
    assert "anchore/sbom-action@" not in workflow
    assert "Download and run checksum-pinned Syft" in "\n".join(rendered_attest)
    assert "8fcb33017a0dc1058298c923c436d19dfa68ae93968e0b423248542e3afb9fc3" in "\n".join(rendered_attest)
    assert "unset ACTIONS_ID_TOKEN_REQUEST_URL ACTIONS_ID_TOKEN_REQUEST_TOKEN" in "\n".join(rendered_attest)
    assert 'spdxVersion == "SPDX-2.3"' in "\n".join(rendered_attest)
    assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in "\n".join(rendered_attest)

    verify_index = next(index for index, text in enumerate(rendered_deploy) if "Verify backend artifact attestations after auth" in text)
    auth_index = next(index for index, text in enumerate(rendered_deploy) if "Authenticate to Google Cloud" in text)
    materialize_index = next(index for index, text in enumerate(rendered_deploy) if "Materialize production env file" in text)
    release_index = next(index for index, text in enumerate(rendered_deploy) if "Run production Cloud Run release" in text)
    assert auth_index < verify_index < materialize_index < release_index
    verify_step = deploy_steps[verify_index]
    verify_env = verify_step.get("env")
    assert isinstance(verify_env, dict)
    assert verify_env.get("SOURCE_DIGEST") == "${{ github.sha }}"
    assert verify_env.get("SIGNER_DIGEST") == "${{ github.workflow_sha }}"
    assert "--native-provenance-snapshot-sha256" in rendered_deploy[verify_index]
    assert "needs.build-backend-artifact.outputs.native_provenance_snapshot_sha256" in rendered_deploy[verify_index]
    assert "--source-digest" in rendered_deploy[verify_index]
    assert "--signer-digest" in rendered_deploy[verify_index]
    assert "gh attestation verify" in verify_helper
    assert "https://spdx.dev/Document/v2.3" in verify_helper
    assert "jq -e" in verify_helper
    for field in ("targetSha", "sourceRepository", "builderWorkflow", "builder", "digest", "nativeProvenanceSnapshotSha256"):
        assert field in verify_helper
    assert 'BUILD_TYPE="${BUILDER_WORKFLOW}#backend-cloud-build-v1"' in verify_helper
    assert 'BUILDER_ID="${BUILDER_WORKFLOW}"' in verify_helper
    assert 'UNDERLYING_BUILDER="https://cloudbuild.googleapis.com/GoogleHostedWorker"' in verify_helper
    assert "cloudBuildProvenance == \"required\"" in verify_helper
    assert "NATIVE_PROVENANCE_SNAPSHOT_SHA256" in verify_helper
    assert '--source-digest "$SOURCE_DIGEST"' in verify_helper
    assert '--signer-digest "$SIGNER_DIGEST"' in verify_helper
    assert 'native_provenance_snapshot_sha256=sha256:' in build_helper
    assert 'Cleanup Google credentials before artifact upload' in "\n".join(rendered_build)
    final_cleanup = deploy_steps[next(index for index, text in enumerate(rendered_deploy) if "Cleanup Google credentials" in text)]
    assert final_cleanup.get("if") == "${{ always() }}"
    assert 'IMAGE_URI="${IMAGE_URI}"' in rendered_deploy[release_index]
    assert "IMAGE_URI" in rendered_deploy[release_index]
    assert "IMAGE_TAG" not in rendered_deploy[release_index]
    assert "BUILD_SERVICE_ACCOUNT" not in rendered_deploy[release_index]
    assert "@sha256:" in deploy_script
    assert "gcloud builds submit" not in deploy_script
    assert "make release-cloud-run" in workflow
    assert "VALIDATE_IN_IMAGE=true" in workflow


def test_artifact_provenance_permissions_are_job_scoped_and_pr_free() -> None:
    """Build, attestation, and deploy permissions stay isolated by job."""
    workflow, _ = _deploy_job_steps()
    parsed = yaml.safe_load(workflow)
    assert isinstance(parsed, dict)
    jobs = parsed["jobs"]
    assert set(jobs) == {
        "verify-target",
        "verify-deploy-identity",
        "authorize-deploy-cutover",
        "prepare-release-artifacts",
        "build-backend-artifact",
        "attest-backend-artifact",
        "deploy",
    }
    deploy = jobs["deploy"]
    assert deploy["permissions"] == {
        "contents": "read",
        "actions": "read",
        "attestations": "read",
        "id-token": "write",
    }
    assert jobs["build-backend-artifact"]["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert jobs["attest-backend-artifact"]["permissions"] == {
        "contents": "read",
        "actions": "read",
        "id-token": "write",
        "attestations": "write",
    }
    assert "pull_request:" not in workflow
    assert "pull_request_target:" not in workflow
    assert "push:" not in workflow
    verify_target = workflow[workflow.index("  verify-target:"): workflow.index("  verify-deploy-identity:")]
    assert "id-token: write" not in verify_target
    assert "attestations: write" not in verify_target
    assert "actions/attest" in workflow
    assert "anchore/sbom-action@" not in workflow
    assert '"underlyingBuilder": "https://cloudbuild.googleapis.com/GoogleHostedWorker"' in workflow
    assert '"cloudBuildProvenance": "required"' in workflow
    assert '"nativeProvenanceSnapshotSha256": native_snapshot' in workflow
    assert '"builder": {"id": os.environ["BUILDER_WORKFLOW"]}' in workflow
    assert "upload-artifact" not in workflow.lower() or "pull_request" not in workflow.lower()


def test_attestation_verification_is_fail_closed_for_identity_and_digest_mismatch() -> None:
    """The verifier compares all identity fields and exits before Cloud Run on failure."""
    workflow, steps = _deploy_job_steps()
    verify_helper = _read("scripts/verify_backend_artifact_attestations.sh")
    verification = "\n".join(
        _step_text(step)
        for step in steps
        if any(
            marker in _step_text(step).lower()
            for marker in ("attestation", "provenance", "verify")
        )
    ) + "\n" + verify_helper
    assert "gh attestation verify" in verification
    assert "--repo" in verification or "--repository" in verification
    assert "--signer-workflow" in verification or "signer_workflow" in verification
    assert "--source-ref" in verification or "source_ref" in verification
    for field in ("target_sha", "repository", "workflow", "builder", "digest"):
        assert field in verification.lower()
    assert "jq -e" in verification or "jq" in verification
    assert "exit 1" in verification
    assert "sbom" in verification.lower()
    deploy_index = workflow.index("Run production Cloud Run release")
    verify_index = workflow.lower().find("verify backend artifact attestations after auth")
    assert verify_index >= 0 and verify_index < deploy_index
