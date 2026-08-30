from __future__ import annotations

from pathlib import Path
import re

import yaml


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


def _extract_trigger_block(on_block: str, trigger: str) -> str:
    m = re.search(rf"(?ms)^  {re.escape(trigger)}:\s*\n(.*?)(?=^  \S|\Z)", on_block)
    assert m, f"Could not locate {trigger} trigger"
    return m.group(1)


def test_ci_triggers_only_main_and_develop() -> None:
    """CI is limited to the two maintained branches and their pull requests."""
    yml = _read_text(".github/workflows/ci.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["push:", "pull_request:"])
    _assert_contains_all(on_block, ["main", "develop"])
    assert "feature/**" not in on_block, "feature branches must not duplicate CI runs"


def test_ci_classifier_exposes_the_stable_gate_interface() -> None:
    """The classifier is the single change-scoped input for CI job selection."""
    ci = _read_text(".github/workflows/ci.yml")

    _assert_contains_all(
        ci,
        [
            "verification_scope:",
            "scripts/classify_verification_inputs.py",
            "--base \"${PR_BASE_SHA}\"",
            "--full",
            "classification_ok != 'true'",
        ],
    )
    for field in (
        "backend",
        "frontend",
        "backend_container",
        "deploy_preflight",
        "governance",
        "workflow_contract",
        "playwright_smoke",
        "playwright_visual",
        "classification_ok",
    ):
        assert f"      {field}: ${{{{ steps.scope.outputs.{field} }}}}" in ci
    assert "elif [ \"${GIT_REF}\" = \"refs/heads/main\" ]; then" in ci


def test_ci_selects_runtime_gates_and_keeps_security_in_backend_suite() -> None:
    ci = _read_text(".github/workflows/ci.yml")
    _assert_contains_all(
        ci,
        [
            "security_text_scan:",
            "name: Backend tests (Python 3.14 + coverage)",
            "python-version: '3.14'",
            "Run backend pytest with coverage",
            "tests/test_security_headers.py",
            "backend_compatibility:",
            "name: Backend compatibility (Python 3.13, no coverage)",
            "github.ref == 'refs/heads/main'",
            "python -m pytest --no-cov",
            "npm test -- --coverage --silent",
            "npm test -- --no-coverage --silent",
            "backend_container:",
            "deploy_preflight:",
            "governance:",
            "python scripts/validate_governance.py",
            "workflow_contract:",
            "quality_gate:",
        ],
    )
    assert "  security_headers:" not in ci


def test_playwright_jobs_are_classifier_scoped_and_parallel() -> None:
    ci = _read_text(".github/workflows/ci.yml")
    assert not Path(".github/workflows/playwright-visual.yml").exists()
    for name, artifact in (("playwright_smoke", "playwright-smoke-artifacts"), ("playwright_visual", "playwright-visual-artifacts")):
        start = ci.index(f"\n  {name}:") + 1
        next_job = re.search(r"\n  [A-Za-z0-9_]+:\n", ci[start + 1 :])
        end = start + 1 + next_job.start() if next_job else len(ci)
        block = ci[start:end]
        assert "      - verification_scope" in block
        assert "      - backend" not in block and "      - frontend" not in block
        assert "failure()" in block
        assert "retention-days: 14" in block
        assert artifact in block


def test_codeql_is_main_scheduled_and_manual_only() -> None:
    yml = _read_text(".github/workflows/codeql.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["push:", "main", "schedule:", "workflow_dispatch:"])
    assert "pull_request:" not in on_block
    assert "develop" not in on_block


def test_full_playwright_is_weekly_manual_with_failure_artifacts() -> None:
    yml = _read_text(".github/workflows/playwright-nightly.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["schedule:", "workflow_dispatch:"])
    assert "pull_request:" not in on_block
    _assert_contains_all(yml, ["if: ${{ failure() }}", "retention-days: 14"])


def test_dependency_review_fails_closed_when_graph_is_unavailable() -> None:
    yml = _read_text(".github/workflows/dependency-review.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["pull_request:", "paths:", ".github/workflows/**", "requirements.txt"])
    _assert_contains_all(yml, ["set -euo pipefail", "Dependency graph is unavailable", "exit 1"])
    _assert_contains_none(yml, ["if: steps.dependency_graph.outputs.supported", "::warning::Dependency review skipped"])


def test_backend_ci_runs_production_314_coverage_and_main_313_compatibility() -> None:
    """The production lane is 3.14 with coverage; 3.13 is main-only without coverage."""
    yml = _read_text(".github/workflows/ci.yml")

    _assert_contains_all(
        yml,
        [
            "name: Backend tests (Python 3.14 + coverage)",
            "python-version: '3.14'",
            "actions/setup-java@v5",
            "distribution: temurin",
            "java-version: '21'",
            "firebase emulators:exec",
            "python -m pytest",
            "backend_compatibility:",
            "name: Backend compatibility (Python 3.13, no coverage)",
            "python-version: '3.13'",
            "python -m pytest --no-cov",
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
        ".github/workflows/production-deploy-preflight.yml",
        ".github/workflows/perf-backend.yml",
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
            "deploy_preflight:",
            "deploy_cloud_run.sh --dry-run",
            "shellcheck scripts/deploy_cloud_run.sh scripts/promote_cloud_run_revision.sh",
            "--no-traffic --traffic-tag candidate",
        ],
    )


def test_deploy_production_workflow_requires_successful_ci_or_manual_main() -> None:
    """Production deployment is gated by a successful main CI run or manual main dispatch."""
    yml = _read_text(".github/workflows/deploy-production.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["workflow_run:", "workflows:", "CI", "completed", "workflow_dispatch:"])
    _assert_contains_none(on_block, ["push:", "pull_request:"])
    _assert_contains_all(yml, ["WORKFLOW_RUN_CONCLUSION", "WORKFLOW_RUN_BRANCH", "conclusion == \"success\"", "TARGET_SHA"])
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
            "Prepare unique deployment marker",
            "secrets.token_hex(16)",
            'echo "::add-mask::${DEPLOYMENT_VERSION}"',
            '--expected-version "${DEPLOYMENT_VERSION}"',
        ],
    )
    assert "EXPECTED_VERSION=" not in yml
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


def test_production_deploy_preflight_is_scheduled_or_manual_read_only() -> None:
    """Production preflight is a read-only scheduled/manual probe."""
    yml = _read_text(".github/workflows/production-deploy-preflight.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["schedule:", "workflow_dispatch:"])
    _assert_contains_none(on_block, ["pull_request:", "pull_request_target:"])
    _assert_contains_all(
        yml,
        [
            "Authenticated deploy read-only probe",
            "--probe-only",
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


def test_all_workflow_yaml_files_parse() -> None:
    workflows = sorted(Path(".github/workflows").glob("*.y*ml"))
    assert workflows
    for path in workflows:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None
