# Repository Hardening Checklist

Last reviewed: 2026-08-31

This checklist tracks GitHub repository settings that cannot be fully changed from the repository contents. Keep exact secret values, production identifiers, and private log details out of this document.

## GitHub Security Settings

- [ ] Secret scanning is enabled.
- [ ] Push protection is enabled.
- [ ] Dependency graph is enabled.
- [ ] Dependabot alerts are enabled.
- [ ] Dependabot security updates are enabled.
- [ ] Code scanning alerts are visible after the CodeQL workflow runs.
- [ ] Dependency review is enabled on dependency and workflow changes.
- [ ] OpenSSF Scorecard advisory results are reviewed after the weekly run.

## GitHub Actions Settings

- [ ] Default workflow permissions are set to read-only.
- [ ] Fork pull request workflows require approval before secrets or privileged jobs can run.
- [ ] No workflow uses `pull_request_target` without a dedicated threat model.

## Branch / Ruleset

- [ ] `main` cannot be force-pushed.
- [ ] `main` cannot be deleted.
- [ ] Required checks are limited to stable, low-noise checks.
- [ ] CodeQL is not required until false positives and runtime are reviewed.
- [ ] Dependency review is required only after false positives are understood.
- [ ] OpenSSF Scorecard is not required while it is advisory-only.

## Production Environment

- [x] `production` environment requires a reviewer and limits deployments to `main`.
- [ ] Deployment secrets are scoped to the production environment where possible.
- [x] Repository variables `GCP_PROJECT_ID`, `GCP_DEPLOY_WIF_PROVIDER`, `GCP_PREFLIGHT_WIF_PROVIDER`, `GCP_DEPLOY_SERVICE_ACCOUNT`, and `GCP_PREFLIGHT_SERVICE_ACCOUNT` are configured without putting their values in source control.
- [ ] Repository variable `GCP_BUILD_SERVICE_ACCOUNT` is configured as a dedicated, non-secret, build-only service-account email.
- [x] Repository variable `PRODUCTION_DEPLOY_ENABLED` is the string `false` and remains fail-closed until the main merge, identity-only exchange, production preflight, and deploy IAM disposition checks are complete.
- [ ] `CLOUD_RUN_ENV_FILE_BASE64` remains the only production deployment secret referenced by the workflows.
- [ ] The legacy long-lived `GCP_SA_KEY` is disabled and deleted only after the WIF exchange and rollback checks documented in [`docs/deployment.md`](../deployment.md) pass.

## Production Deployment Invariants

The source-controlled deployment contract is:

- `Deploy to production` accepts an automatic `workflow_run` only when the completed workflow is `CI` with `success`, `push`, `main`, and the requested `head_sha`.
- CI authorization also pins `.github/workflows/ci.yml` to live workflow ID `187172373` and requires the same run's canonical `Quality gate` job to be completed successfully; a recreated workflow requires an explicit constant update.
- Manual break-glass requires an explicit `target_sha` and a dispatch from the trusted `main` ref; the workflow queries GitHub Actions for a matching successful `CI` push on `main` before entering the `production` environment. The optional `identity_exchange_only=true` path still requires this target/Quality gate verification and only checks deploy WIF token exchange.
- Normal automatic/manual deployment requires `authorize-deploy-cutover` to verify the repository variable `PRODUCTION_DEPLOY_ENABLED` is the literal string `true`; the deploy job needs both the target verifier and this guard. Identity-only runs skip the guard and deploy job, while normal PR jobs and runners are unchanged.
- `prepare-release-artifacts`, `build-backend-artifact`, `attest-backend-artifact`, and `deploy` are four jobs in the existing production workflow. Prepare checks out that exact SHA, builds the frontend, and uploads a one-day handoff artifact. Build checks out and asserts `git rev-parse HEAD`; `scripts/build_backend_artifact.sh` creates a mode-700 private context with `git archive TARGET_SHA` and submits it to Cloud Build exactly once; dirty, ignored, and untracked files cannot enter the context. The one Cloud Build input tag and runtime `GIT_SHA` are derived from that checkout and cannot be overridden by the deployment env file; Cloud Run receives only the verified full `IMAGE_URI` (`@sha256:<64-hex>`). Attest downloads the exact image archive, runs the checksum-pinned Syft 1.51.1 CLI against the local Docker daemon image, and writes GitHub workflow-level attestations. Deploy downloads only the handoff artifacts and performs the final private-GAR verification and digest-only release.
- The `build-backend-artifact` and `deploy` jobs, plus authenticated preflight and the manual main identity-only job, use job-scoped Workload Identity Federation for their Cloud Build, private-GAR verification, and probe needs. `attest-backend-artifact` has only the job-scoped GitHub OIDC permission required by `actions/attest` and receives no Google credential; `verify-target`, `prepare-release-artifacts`, `authorize-deploy-cutover`, and normal PR/CI jobs do not receive `id-token: write`.
- Both production workflows are key-free: deploy uses `GCP_DEPLOY_SERVICE_ACCOUNT`, preflight uses the separate `GCP_PREFLIGHT_SERVICE_ACCOUNT`, and neither contains `credentials_json` or `GCP_SA_KEY` fallback. The existing full-SHA action pins, CI/Quality gate authorization, canary, health check, rollback, and materialized env-file cleanup remain part of the contract.
- Cloud Build is submitted with the explicit `projects/<PROJECT_ID>/serviceAccounts/<GCP_BUILD_SERVICE_ACCOUNT>` resource; the project default service account is not selected implicitly. The canonical `cloudbuild.backend.yaml` sets `options.logging: CLOUD_LOGGING_ONLY`, and the dedicated build service account is expected to have `roles/logging.logWriter`. Identity-only, preflight, and PR/CI jobs do not receive the build service account variable. Native provenance lookup uses `containeranalysis.googleapis.com`; the deploy service account has project-level `roles/containeranalysis.occurrences.viewer` and the API is enabled in the live target project.
- Cloud Build source staging uses the archived target SHA's explicit `.gcloudignore` allowlist, limited to the Dockerfile, build config, requirements, and backend runtime source. Tracked env, credential, and generated paths are excluded before upload. Native provenance must contain exactly one non-empty inline `buildConfig` or an exact SCM `buildConfigSource`.
- `build-backend-artifact` compares the Cloud Build result with the Artifact Registry manifest digest and obtains native provenance for that exact digest with `--show-provenance`. It verifies the image digest, GoogleHostedWorker, invocation, and `_SOURCE_REPOSITORY` / `_TARGET_SHA` / `_BUILDER_WORKFLOW` substitutions. SCM metadata may be absent for the local archive; when present, repository/ref/SHA are checked strictly. The verified JSON is SHA256-bound into `nativeProvenanceSnapshotSha256`. It also runs the health smoke against the exact digest. `attest-backend-artifact` runs checksum-pinned Syft 1.51.1 to produce strict SPDX 2.3 JSON; it does not use an Anchore Action. It then creates GitHub workflow-level delivery provenance and SBOM attestations. In GitHub's verification certificate, `--source-digest` is the source repository digest (`github.sha`) and `--signer-digest` is the workflow file revision (`github.workflow_sha`); the build target `TARGET_SHA` remains a separate custom-predicate field. The SLSA `runDetails.builder.id` is the exact production `BUILDER_WORKFLOW` URI and its repo-resolving `buildDefinition.buildType` is `${BUILDER_WORKFLOW}#backend-cloud-build-v1`; `underlyingBuilder=https://cloudbuild.googleapis.com/GoogleHostedWorker` and `cloudBuildProvenance=required` are predicate values checked as the claimed upstream Cloud Build native provenance. The GitHub signer identity is the workflow certificate, not the Google builder identity. Cloud Build native provenance is independently required with `options.requestedVerifyOption: VERIFIED`. Google credentials are removed before Syft/actions/attest and re-authenticated in the deploy job immediately before private-GAR `gh attestation verify`. A missing or mismatched source digest, signer digest, target SHA, repository, signer workflow, builder, digest, native provenance, or SBOM fails closed before Cloud Run, traffic, or Hosting writes.
- The production workflow has no unconditional PR publish path for backend images, SBOMs, or attestations. No new workflow is introduced; the four handoff jobs are added inside the existing workflow because job-wide OIDC/permissions and build, Syft/attestation, and deployment dependencies must remain isolated. The normal exact-SHA, CI/Quality gate, candidate/canary/health/rollback, and materialized env cleanup remain required. `build-backend-artifact` and `deploy` both use the `production` environment, so an environment approval may occur at each job; the manual identity-only path is also environment-bound but performs only WIF exchange.
- GitHub attestation repository API storage and Artifact Registry image/native-provenance retention are external settings. The helper exposes only `image_name`, `image_digest`, `image_uri`, and `native_provenance_snapshot_sha256` through `GITHUB_OUTPUT`; the Cloud Build build ID is kept internal and is not emitted. The frontend, backend image archive, and attestation metadata handoffs are retained for one day. Keep only synthetic placeholders and never place secrets, tokens, `.env.deploy`, or private registry credentials in an image, SBOM, attestation, summary, or log.
- The native provenance read requires `containeranalysis.googleapis.com` and project-level `roles/containeranalysis.occurrences.viewer` for the deploy service account; concrete production identifiers remain outside this repository. Release operations own the first failing stage: build/IAM failures go to the build owner, SPDX/attestation failures to the security/release owner, and Cloud Run/Hosting/canary/rollback failures to the deploy owner. Each job removes its workspace, temporary archive/SBOM, generated env, and credentials; rollback evidence remains retained.
- The four-job split is not sunset or demoted automatically. It may be changed only after authorized releases demonstrate stable digest/provenance/rollback behavior, one-day artifact cleanup is confirmed, runner/Cloud Build quota and GitHub/Artifact Registry storage costs are measured and accepted, and job-wide OIDC/tool isolation is no longer required. An Issue/PR must preserve source/signer/target separation, exact-digest attestation, credential cleanup, and rollback gates. Repeated Syft, native provenance, or GitHub attestation failures keep cutover fail-closed rather than permitting a verification bypass.
- Authenticated preflight runs from scheduled or `main`-ref manual execution only, always checks out trusted `main`, and fails closed when WIF inputs are unavailable or malformed. Static validation belongs to the `CI` lane.

## External configuration checks

Checked items were verified against live GitHub/GCP configuration on the review date. Unchecked items remain merge or retirement blockers:

- [x] GitHub `production` environment has one required reviewer and a `main`-only deployment branch policy; WIF variables and current deployment secrets are repository-scoped as recorded above.
- [x] Initial `PRODUCTION_DEPLOY_ENABLED=false`; enable it only after the main merge, successful identity-only exchange, successful authenticated preflight, and deploy IAM disposition.
- [x] The Workload Identity Pool and separate deploy/preflight providers are active, with numeric repository/owner IDs, exact `workflow_ref`, main ref, and deploy-only `production` environment conditions documented in [`docs/deployment.md`](../deployment.md).
- [x] `roles/iam.workloadIdentityUser` uses separate exact deploy-environment/preflight-main subjects, and the preflight service account has only the custom Firestore index-list role plus `roles/firebasehosting.viewer`.
- [ ] The deploy service account's existing Cloud Run / Cloud Build / Artifact Registry / Firestore / Firebase Hosting roles are reduced to demonstrated requirements; broad legacy viewer, storage admin, and service-usage admin roles still require evidence-led review.
- [x] `containeranalysis.googleapis.com` is enabled and the deploy service account has project-level `roles/containeranalysis.occurrences.viewer` for exact-digest native provenance reads; concrete project and account identifiers remain outside this repository.
- [ ] The dedicated build service account has `roles/logging.logWriter` and only the additional build input/output roles confirmed by live IAM inventory.
- [ ] Successful token exchange and authenticated preflight against the configured project, plus production canary/health/rollback behavior after WIF is enabled.
- [ ] Disable/delete state of the legacy `GCP_SA_KEY`; retain it only for an explicitly authorized rollback window until the external WIF checks complete.
- [ ] GitHub attestation API storage/retention and signer workflow policy are confirmed for the production repository.
- [ ] Artifact Registry image, failed-tag cleanup, Cloud Build log, and native provenance retention are confirmed with an owner and rollback window.
- [ ] Additional runner wall time, Cloud Build quota, and GitHub/Artifact Registry storage cost are measured after the first authorized release.

The unchecked external checks must be completed or explicitly dispositioned before treating the repository change as merge-ready. This checklist does not infer runtime success from static workflow validation.

## Manual Review Notes

- Date:
- Reviewer:
- Remaining gaps:
