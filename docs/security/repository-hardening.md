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

- [ ] `production` environment is protected.
- [ ] Deployment secrets are scoped to the production environment where possible.
- [x] Repository variables `GCP_PROJECT_ID`, `GCP_DEPLOY_WIF_PROVIDER`, `GCP_PREFLIGHT_WIF_PROVIDER`, `GCP_DEPLOY_SERVICE_ACCOUNT`, and `GCP_PREFLIGHT_SERVICE_ACCOUNT` are configured without putting their values in source control.
- [ ] `CLOUD_RUN_ENV_FILE_BASE64` remains the only production deployment secret referenced by the workflows.
- [ ] The legacy long-lived `GCP_SA_KEY` is disabled and deleted only after the WIF exchange and rollback checks documented in [`docs/deployment.md`](../deployment.md) pass.

## Production Deployment Invariants

The source-controlled deployment contract is:

- `Deploy to production` accepts an automatic `workflow_run` only when the completed workflow is `CI` with `success`, `push`, `main`, and the requested `head_sha`.
- CI authorization also pins `.github/workflows/ci.yml` to live workflow ID `187172373` and requires the same run's canonical `Quality gate` job to be completed successfully; a recreated workflow requires an explicit constant update.
- Manual break-glass requires an explicit `target_sha` and a dispatch from the trusted `main` ref; the workflow queries GitHub Actions for a matching successful `CI` push on `main` before entering the `production` environment.
- The deploy job checks out that exact SHA and asserts `git rev-parse HEAD`. `IMAGE_TAG` and runtime `GIT_SHA` are derived from that checkout and cannot be overridden by the deployment env file.
- The deploy job and authenticated preflight use the pinned `google-github-actions/auth` action with Workload Identity Federation; `id-token: write` is scoped to those jobs, and `verify-target` does not receive it.
- Both production workflows are key-free: deploy uses `GCP_DEPLOY_SERVICE_ACCOUNT`, preflight uses the separate `GCP_PREFLIGHT_SERVICE_ACCOUNT`, and neither contains `credentials_json` or `GCP_SA_KEY` fallback. The existing full-SHA action pins, CI/Quality gate authorization, canary, health check, rollback, and materialized env-file cleanup remain part of the contract.
- Authenticated preflight runs from scheduled or `main`-ref manual execution only, always checks out trusted `main`, and fails closed when WIF inputs are unavailable or malformed. Static validation belongs to the `CI` lane.

## External configuration checks

Checked items were verified against live GitHub/GCP configuration on the review date. Unchecked items remain merge or retirement blockers:

- [ ] GitHub `production` environment protection and the effective scope of repository variables/secrets.
- [x] The Workload Identity Pool and separate deploy/preflight providers are active, with numeric repository/owner IDs, exact `workflow_ref`, main ref, and deploy-only `production` environment conditions documented in [`docs/deployment.md`](../deployment.md).
- [x] `roles/iam.workloadIdentityUser` uses separate exact deploy-environment/preflight-main subjects, and the preflight service account has only the custom Firestore index-list role plus `roles/firebasehosting.viewer`.
- [ ] The deploy service account's existing Cloud Run / Cloud Build / Artifact Registry / Firestore / Firebase Hosting roles are reduced to demonstrated requirements; broad legacy viewer, storage admin, and service-usage admin roles still require evidence-led review.
- [ ] Successful token exchange and authenticated preflight against the configured project, plus production canary/health/rollback behavior after WIF is enabled.
- [ ] Disable/delete state of the legacy `GCP_SA_KEY`; retain it only for an explicitly authorized rollback window until the external WIF checks complete.

The unchecked external checks must be completed or explicitly dispositioned before treating the repository change as merge-ready. This checklist does not infer runtime success from static workflow validation.

## Manual Review Notes

- Date:
- Reviewer:
- Remaining gaps:
