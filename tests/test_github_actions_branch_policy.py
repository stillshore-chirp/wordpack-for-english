from __future__ import annotations

from pathlib import Path
import re


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _assert_contains_all(text: str, needles: list[str]) -> None:
    missing = [n for n in needles if n not in text]
    assert not missing, f"Missing expected snippets: {missing}"


def _assert_contains_none(text: str, needles: list[str]) -> None:
    present = [n for n in needles if n in text]
    assert not present, f"Found forbidden snippets: {present}"


def _extract_on_block(yml: str) -> str:
    """
    Extracts the "on:" block up to the next top-level key (best-effort).
    This avoids binding tests to exact YAML formatting (inline list vs multiline list).
    """
    m = re.search(r"(?ms)^\s*on:\s*\n(.*?)(?=^\S)", yml)
    assert m, "Could not locate top-level 'on:' block"
    return m.group(1)


def test_ci_runs_on_develop_and_prs_to_develop() -> None:
    """
    Contract: develop remains a day-to-day CI target even though main is the default branch.
    CI must run for pushes to develop and PRs targeting develop.
    """
    yml = _read_text(".github/workflows/ci.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["push:", "pull_request:"])
    assert "develop" in on_block, "CI must include develop in its triggers"


def test_deploy_dry_run_is_main_only() -> None:
    """
    Contract: main is the production deployment branch.
    Anything that authenticates to GCP must not run on develop.
    """
    yml = _read_text(".github/workflows/deploy-dry-run.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(
        on_block,
        [
            "workflow_run:",
            "workflows:",
            "CI",
            "types:",
            "completed",
        ],
    )
    _assert_contains_all(
        yml,
        [
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.event == 'push'",
        ],
    )
    assert "develop" not in yml, "deploy-dry-run must not run on develop"
    # Sanity: ensure this workflow is actually the one touching GCP.
    _assert_contains_all(yml, ["google-github-actions/auth@v2", "setup-gcloud@v3"])


def test_backend_ci_runs_real_pytest_on_supported_python_versions() -> None:
    """Contract: backend CI must run pytest with Java 21 and propagate failures."""
    yml = _read_text(".github/workflows/ci.yml")

    _assert_contains_all(
        yml,
        [
            "python-version: ['3.13', '3.14']",
            "actions/setup-java@v5",
            "distribution: temurin",
            "java-version: '21'",
            'firebase emulators:exec --only firestore --project "${FIRESTORE_PROJECT_ID}" --config firebase.json "python -m pytest"',
        ],
    )
    _assert_contains_none(yml, ["pytest | cat", '"pytest" | cat'])


def test_backend_ci_builds_and_health_checks_python_314_container() -> None:
    """Contract: Python 3.14 compatibility includes the production Docker path."""
    yml = _read_text(".github/workflows/ci.yml")

    _assert_contains_all(
        yml,
        [
            "backend_container:",
            "--build-arg PYTHON_VERSION=3.14",
            "-f Dockerfile.backend",
            "--env FIRESTORE_PROJECT_ID=wordpack-ci",
            "http://127.0.0.1:8080/healthz",
        ],
    )


def test_production_runtime_and_single_version_jobs_default_to_python_314() -> None:
    """Contract: production uses 3.14 while backend CI keeps the 3.13 compatibility lane."""
    dockerfile = _read_text("Dockerfile.backend")
    assert "ARG PYTHON_VERSION=3.14" in dockerfile

    single_version_workflows = [
        ".github/workflows/deploy-production.yml",
        ".github/workflows/deploy-dry-run.yml",
        ".github/workflows/production-deploy-preflight.yml",
        ".github/workflows/perf-backend.yml",
        ".github/workflows/playwright-visual.yml",
        ".github/workflows/playwright-nightly.yml",
    ]
    for path in single_version_workflows:
        yml = _read_text(path)
        assert "3.14" in yml, f"{path} must use Python 3.14"
        assert "3.13" not in yml, f"{path} must not remain pinned to Python 3.13"


def test_ci_does_not_embed_production_deploy_job() -> None:
    """
    Contract: production deployment is owned by deploy-production.yml.
    CI may run guards and dry-runs, but it must not contain the production deploy job.
    """
    yml = _read_text(".github/workflows/ci.yml")
    _assert_contains_none(
        yml,
        [
            "deploy_production:",
            "environment: production",
        ],
    )
    _assert_contains_all(
        yml,
        [
            "cloud_run_guard:",
            "deploy_cloud_run.sh --dry-run",
            "shellcheck scripts/deploy_cloud_run.sh scripts/promote_cloud_run_revision.sh",
            "--no-traffic --traffic-tag candidate",
        ],
    )


def test_deploy_production_workflow_runs_on_main_push_or_manual_only() -> None:
    """
    Contract: automatic production deploy runs from the standalone workflow on main push.
    workflow_dispatch remains as the manual fallback, and workflow_run is not used.
    """
    yml = _read_text(".github/workflows/deploy-production.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["push:", "branches:", "main", "workflow_dispatch:"])
    _assert_contains_none(on_block, ["workflow_run:", "pull_request:"])
    _assert_contains_none(yml, ["github.event.workflow_run."])
    assert "cancel-in-progress: false" in yml


def test_deploy_production_promotes_a_health_checked_no_traffic_candidate() -> None:
    """Contract: Hosting deploy waits for the staged Cloud Run rollout to succeed."""
    yml = _read_text(".github/workflows/deploy-production.yml")

    _assert_contains_all(
        yml,
        [
            "NO_TRAFFIC=true",
            'TRAFFIC_TAG="${CLOUD_RUN_TRAFFIC_TAG}"',
            "scripts/promote_cloud_run_revision.sh",
            '--canary-percent "${CLOUD_RUN_CANARY_PERCENT}"',
            '--attempts "${CLOUD_RUN_CANARY_ATTEMPTS}"',
            '--delay-seconds "${CLOUD_RUN_CANARY_DELAY_SECONDS}"',
            '--requests-per-attempt "${CLOUD_RUN_CANARY_REQUESTS_PER_ATTEMPT}"',
            '--health-url "https://${FIREBASE_PROJECT_ID}.web.app/api/config"',
            '--expected-version "${EXPECTED_VERSION}"',
        ],
    )
    assert yml.index("Promote staged Cloud Run revision") < yml.index("Deploy Firebase Hosting")


def test_deploy_production_uses_api_based_hosting_deploy() -> None:
    """
    Contract: production deploy must not pass a gcloud access token as
    FIREBASE_TOKEN. Firestore index sync and Firebase Hosting deploy both use
    gcloud-authenticated API requests, avoiding Firebase CLI auth in CI.
    """
    yml = _read_text(".github/workflows/deploy-production.yml")

    _assert_contains_all(
        yml,
        [
            "google-github-actions/auth@v2",
            "credentials_json: ${{ secrets.GCP_SA_KEY }}",
            "create_credentials_file: true",
            "export_environment_variables: true",
            "python scripts/deploy_firebase_hosting.py",
            "--site \"${FIREBASE_PROJECT_ID}\"",
            "npm --prefix ./apps/frontend run build",
            "TOOL=gcloud",
        ],
    )
    _assert_contains_none(
        yml,
        [
            "FIREBASE_TOKEN",
            "firebase deploy --only hosting",
            "npm install -g firebase-tools",
            "Prepare Firebase CLI credentials file",
            "gcloud auth print-access-token",
            "Prepare Firebase CLI auth token",
            "TOOL=firebase",
        ],
    )


def test_production_deploy_preflight_checks_prs_without_deploying() -> None:
    """
    Contract: PRs get a non-deploying production preflight. Static checks run on
    the PR code without secrets, while the authenticated probe uses
    pull_request_target and trusted base code for read-only API checks.
    """
    yml = _read_text(".github/workflows/production-deploy-preflight.yml")
    on_block = _extract_on_block(yml)

    _assert_contains_all(
        on_block,
        [
            "pull_request:",
            "pull_request_target:",
            "workflow_dispatch:",
            "branches:",
            "main",
        ],
    )
    _assert_contains_all(
        yml,
        [
            "Static deploy preflight",
            "Authenticated deploy read-only probe",
            "production-deploy-preflight-${{ github.workflow }}-${{ github.event_name }}-",
            "github.event_name == 'pull_request' || github.event_name == 'workflow_dispatch'",
            "github.event_name == 'pull_request_target' || github.event_name == 'workflow_dispatch'",
            "ref: ${{ github.event.pull_request.base.sha }}",
            "--plan-only",
            "--probe-only",
            "deploy_cloud_run.sh \\",
            "gcloud auth print-access-token --quiet >/dev/null",
            "pageSize=0",
            "google-github-actions/auth@v2",
            "scripts/deploy_firebase_hosting.py",
        ],
    )
    _assert_contains_none(
        yml,
        [
            "environment: production",
            "firebase deploy --only hosting",
            "pageSize=1",
        ],
    )
