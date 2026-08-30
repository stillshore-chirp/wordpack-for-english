# Repository Hardening Checklist

Last reviewed: 2026-08-30

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
- [ ] Long-lived `GCP_SA_KEY` migration to Workload Identity Federation is tracked separately.

## Production Deployment Invariants

The source-controlled deployment contract is:

- `Deploy to production` accepts an automatic `workflow_run` only when the completed workflow is `CI` with `success`, `push`, `main`, and the requested `head_sha`.
- CI authorization also pins `.github/workflows/ci.yml` to live workflow ID `187172373` and requires the same run's canonical `Quality gate` job to be completed successfully; a recreated workflow requires an explicit constant update.
- Manual break-glass requires an explicit `target_sha` and a dispatch from the trusted `main` ref; the workflow queries GitHub Actions for a matching successful `CI` push on `main` before entering the `production` environment.
- The deploy job checks out that exact SHA and asserts `git rev-parse HEAD`. `IMAGE_TAG` and runtime `GIT_SHA` are derived from that checkout and cannot be overridden by the deployment env file.
- Authenticated preflight runs from scheduled or `main`-ref manual execution only, always checks out trusted `main`, and fails closed when credentials are unavailable. Static validation belongs to the `CI` lane.

The live branch rules, environment approvals, secret scope, and identity-provider configuration remain operational settings and must be verified in GitHub/GCP; this file does not claim those settings are currently enabled.

## Manual Review Notes

- Date:
- Reviewer:
- Remaining gaps:
