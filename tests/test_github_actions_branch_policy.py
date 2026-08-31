from __future__ import annotations

from pathlib import Path
import re

import yaml


_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_EXTERNAL_ACTION_RE = re.compile(
    r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:/[^@\s]+)?@(?P<ref>[^@\s]+)$"
)
_VERSION_COMMENT_RE = re.compile(
    r"(?:^|\s)#\s*v\d+(?:\.\d+){0,2}(?:[-+][0-9A-Za-z.-]+)?(?:\s|$)"
)


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _read_workflow_job(path: str, job_id: str) -> dict[str, object]:
    workflow = yaml.safe_load(_read_text(path))
    assert isinstance(workflow, dict)
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    job = jobs.get(job_id)
    assert isinstance(job, dict)
    return job


def _assert_contains_all(text: str, needles: list[str]) -> None:
    missing = [n for n in needles if n not in text]
    assert not missing, f"Missing expected snippets: {missing}"


def _assert_contains_none(text: str, needles: list[str]) -> None:
    present = [n for n in needles if n in text]
    assert not present, f"Found forbidden snippets: {present}"


def _iter_step_uses_lines(yml: str) -> list[tuple[object, str]]:
    """Return step-level YAML ``uses`` keys, not reusable workflows or run text."""
    root = yaml.compose(yml, Loader=yaml.SafeLoader)
    assert root is not None
    lines = yml.splitlines()
    references: list[tuple[object, str]] = []
    active_nodes: set[int] = set()

    def visit(node: yaml.Node, context: str = "root") -> None:
        node_id = id(node)
        if node_id in active_nodes:
            return
        active_nodes.add(node_id)
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                key_name = key.value if isinstance(key, yaml.ScalarNode) else None
                if (
                    context == "step"
                    and isinstance(key, yaml.ScalarNode)
                    and key.value == "uses"
                ):
                    references.append(
                        (
                            value.value
                            if isinstance(value, yaml.ScalarNode)
                            else None,
                            lines[key.start_mark.line],
                        )
                    )
                child_context = "other"
                if context == "root" and key_name == "jobs":
                    child_context = "jobs"
                elif context == "jobs" and isinstance(value, yaml.MappingNode):
                    child_context = "job"
                elif (
                    context == "job"
                    and key_name == "steps"
                    and isinstance(value, yaml.SequenceNode)
                ):
                    child_context = "steps"
                visit(value, child_context)
        elif isinstance(node, yaml.SequenceNode):
            for item in node.value:
                visit(item, "step" if context == "steps" else "other")
        active_nodes.remove(node_id)

    visit(root)
    return references


def _classify_step_uses_reference(value: object) -> str:
    if not isinstance(value, str):
        return "unknown"
    if value.startswith(("./", "../")):
        return "local"
    if value.startswith("docker://"):
        return "docker"
    target = value.rsplit("@", 1)[0]
    if "/.github/workflows/" in target:
        return "unknown"
    if _EXTERNAL_ACTION_RE.fullmatch(value) is not None:
        return "external"
    return "unknown"


def _external_action_pin_violations(yml: str) -> list[str]:
    violations: list[str] = []
    for value, source_line in _iter_step_uses_lines(yml):
        reference_kind = _classify_step_uses_reference(value)
        if reference_kind in {"local", "docker"}:
            continue
        if reference_kind == "unknown":
            display_value = value if isinstance(value, str) else "<non-scalar>"
            violations.append(
                f"{display_value}: unsupported step-level uses reference"
            )
            continue
        assert isinstance(value, str)
        ref = value.rsplit("@", 1)[1]
        if _FULL_SHA_RE.fullmatch(ref) is None:
            violations.append(f"{value}: full lowercase SHA required")
        if _VERSION_COMMENT_RE.search(source_line) is None:
            violations.append(f"{value}: inline version comment required")
    return violations


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
        "dependency_review",
        "playwright_smoke",
        "playwright_visual",
        "playwright_targeted",
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
            "dependency_review:",
            "uses: actions/dependency-review-action@",
            "Dependency graph is unavailable",
            "DEPENDENCY_SELECTED:",
            "DEPENDENCY_SELECTED: ${{ github.event_name == 'pull_request' && needs.verification_scope.outputs.dependency_review == 'true' }}",
            "      - dependency_review",
            'check_selected "${DEPENDENCY_SELECTED}" "${DEPENDENCY_RESULT}" dependency_review',
            "tests/test_scheduled_maintenance_workflow.py",
            "quality_gate:",
        ],
    )
    assert "  security_headers:" not in ci


def test_governance_job_runs_contract_tests_after_validation() -> None:
    """The governance job owns the validator and its focused contract tests."""
    job = _read_workflow_job(".github/workflows/ci.yml", "governance")
    steps = job.get("steps")
    assert isinstance(steps, list)
    runs = [
        step["run"]
        for step in steps
        if isinstance(step, dict) and isinstance(step.get("run"), str)
    ]

    validator_index = next(
        index for index, run in enumerate(runs) if "python scripts/validate_governance.py" in run
    )
    pytest_index = next(
        index for index, run in enumerate(runs) if "python -m pytest -q --no-cov" in run
    )
    assert validator_index < pytest_index

    pytest_run = runs[pytest_index]
    for test_path in (
        "tests/test_agent_harness_budget.py",
        "tests/test_governance_task_state.py",
        "tests/test_validate_governance.py",
        "tests/test_public_docs_security.py",
        "tests/test_security_scan_text.py",
    ):
        assert test_path in pytest_run


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


def test_targeted_full_specs_reuse_smoke_job_and_quality_gate() -> None:
    ci = _read_text(".github/workflows/ci.yml")
    smoke_start = ci.index("\n  playwright_smoke:") + 1
    visual_start = ci.index("\n  playwright_visual:") + 1
    smoke = ci[smoke_start:visual_start]
    quality_start = ci.index("\n  quality_gate:") + 1
    quality = ci[quality_start:]

    _assert_contains_all(
        ci,
        [
            "playwright_targeted: ${{ steps.scope.outputs.playwright_targeted }}",
            "playwright_targeted_specs: ${{ steps.scope.outputs.playwright_targeted_specs }}",
        ],
    )
    _assert_contains_all(
        smoke,
        [
            "needs.verification_scope.outputs.playwright_targeted == 'true'",
            "TARGETED_FULL_SPECS: ${{ needs.verification_scope.outputs.playwright_targeted_specs }}",
            "REGISTERED_FULL_E2E_SPECS",
            "json.loads(os.environ.get(\"TARGETED_FULL_SPECS\") or \"[]\")",
            "len(requested_specs) != len(set(requested_specs))",
            "spec not in REGISTERED_FULL_E2E_SPECS",
            "selected_specs = list(dict.fromkeys(selected_specs))",
            "subprocess.run(",
            "*selected_specs",
        ],
    )
    assert "${{ needs.verification_scope.outputs.playwright_targeted_specs }}" not in (
        smoke.rsplit("run: |", 1)[1]
    )
    _assert_contains_all(
        quality,
        [
            "SMOKE_SELECTED: ${{ needs.verification_scope.outputs.playwright_smoke == 'true' || needs.verification_scope.outputs.playwright_targeted == 'true' }}",
            'check_selected "${SMOKE_SELECTED}" "${SMOKE_RESULT}" playwright_smoke',
        ],
    )


def test_codeql_is_scheduled_and_manual_only() -> None:
    yml = _read_text(".github/workflows/scheduled-maintenance.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["schedule:", "workflow_dispatch:", "suite:"])
    _assert_contains_none(on_block, ["push:", "pull_request:", "workflow_run:"])
    _assert_contains_all(
        yml,
        [
            "  codeql:",
            "uses: github/codeql-action/init@",
            "uses: github/codeql-action/analyze@",
        ],
    )


def test_full_playwright_is_weekly_manual_with_failure_artifacts() -> None:
    yml = _read_text(".github/workflows/scheduled-maintenance.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(on_block, ["schedule:", "workflow_dispatch:"])
    assert "pull_request:" not in on_block
    _assert_contains_all(yml, ["  playwright:", "if: ${{ failure() }}", "retention-days: 14"])


def test_dependency_review_is_ci_only_and_fails_closed_when_graph_is_unavailable() -> None:
    ci = _read_text(".github/workflows/ci.yml")
    assert not Path(".github/workflows/dependency-review.yml").exists()
    _assert_contains_all(
        ci,
        [
            "dependency_review: ${{ steps.scope.outputs.dependency_review }}",
            "github.event_name == 'pull_request'",
            "needs.verification_scope.outputs.dependency_review == 'true'",
            "permissions:\n      contents: read\n      pull-requests: read",
            "gh api \"repos/${GITHUB_REPOSITORY}/dependency-graph/compare/${BASE_SHA}...${HEAD_SHA}\"",
            "Dependency graph is unavailable",
            "exit 1",
            "uses: actions/dependency-review-action@",
        ],
    )
    assert ci.count(
        "uses: actions/dependency-review-action@"
    ) == 1


def test_only_ci_is_an_automatic_pull_request_workflow_and_allowlist_is_bounded() -> None:
    workflows = sorted(Path(".github/workflows").glob("*.y*ml"))
    assert len(workflows) <= 5
    automatic_pr_workflows = [
        path.name
        for path in workflows
        if re.search(r"(?m)^  pull_request(?:_target)?:", _extract_on_block(_read_text(str(path))))
    ]
    assert len(automatic_pr_workflows) <= 5
    assert automatic_pr_workflows == ["ci.yml"]


def test_backend_ci_runs_production_314_coverage_and_main_313_compatibility() -> None:
    """The production lane is 3.14 with coverage; 3.13 is main-only without coverage."""
    yml = _read_text(".github/workflows/ci.yml")

    _assert_contains_all(
        yml,
        [
            "name: Backend tests (Python 3.14 + coverage)",
            "python-version: '3.14'",
            "uses: actions/setup-java@",
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
    assert "Prepare production-like env file" not in yml


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
        ".github/workflows/scheduled-maintenance.yml",
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


def test_deploy_preflight_runs_focused_behavioral_contracts() -> None:
    """Deploy-only changes run deploy behavior contracts without backend full pytest."""
    yml = _read_text(".github/workflows/ci.yml")
    start = yml.index("\n  deploy_preflight:")
    end = yml.index("\n  governance:", start)
    block = yml[start:end]

    _assert_contains_all(
        block,
        [
            "Run focused deploy behavior tests",
            "needs.verification_scope.outputs.deploy_preflight == 'true'",
            "github.event_name == 'push' && github.ref == 'refs/heads/main'",
            "python -m pytest -q --no-cov",
            "tests/config/test_firebase_config.py",
            "tests/test_cloud_build_config.py",
            "tests/test_deploy_script_env_guard.py",
            "tests/test_firebase_hosting_deploy.py",
            "tests/test_promote_cloud_run_revision.py",
            "tests/test_deploy_workflow_safety.py",
        ],
    )
    assert "python -m pytest\n" not in block


def test_deploy_production_workflow_requires_successful_ci_or_manual_main() -> None:
    """Production deployment is gated by a successful main CI run or manual main dispatch."""
    yml = _read_text(".github/workflows/deploy-production.yml")
    on_block = _extract_on_block(yml)
    _assert_contains_all(
        on_block,
        [
            "workflow_run:",
            "workflows:",
            "CI",
            "completed",
            "workflow_dispatch:",
            "identity_exchange_only:",
            "required: false",
            "default: false",
            "type: boolean",
        ],
    )
    _assert_contains_none(on_block, ["push:", "pull_request:"])
    _assert_contains_all(yml, ["WORKFLOW_RUN_CONCLUSION", "WORKFLOW_RUN_BRANCH", "conclusion == \"success\"", "TARGET_SHA"])
    assert "cancel-in-progress: false" in yml


def test_deploy_cutover_guard_and_identity_exchange_are_scoped() -> None:
    """Identity exchange is a manual main-only probe; normal deploys are fail-closed."""
    path = ".github/workflows/deploy-production.yml"
    yml = _read_text(path)
    identity = _read_workflow_job(path, "verify-deploy-identity")
    guard = _read_workflow_job(path, "authorize-deploy-cutover")
    deploy = _read_workflow_job(path, "deploy")

    assert identity["needs"] == "verify-target"
    assert identity["if"] == (
        "github.event_name == 'workflow_dispatch' && "
        "github.ref == 'refs/heads/main' && inputs.identity_exchange_only == true"
    )
    assert identity["environment"] == "production"
    assert guard["needs"] == "verify-target"
    assert guard["if"] == (
        "needs.verify-target.result == 'success' && "
        "(github.event_name != 'workflow_dispatch' || inputs.identity_exchange_only != true)"
    )
    assert guard["env"] == {
        "PRODUCTION_DEPLOY_ENABLED": "${{ vars.PRODUCTION_DEPLOY_ENABLED }}"
    }
    assert deploy["needs"] == ["verify-target", "authorize-deploy-cutover"]
    assert deploy["if"] == (
        "needs.verify-target.result == 'success' && "
        "needs.authorize-deploy-cutover.result == 'success' && "
        "(github.event_name != 'workflow_dispatch' || inputs.identity_exchange_only != true)"
    )

    identity_start = yml.index("  verify-deploy-identity:")
    identity_end = yml.index("  authorize-deploy-cutover:", identity_start)
    identity_block = yml[identity_start:identity_end]
    _assert_contains_all(
        identity_block,
        [
            "permissions:\n      id-token: write",
            "GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}",
            "GCP_DEPLOY_WIF_PROVIDER: ${{ vars.GCP_DEPLOY_WIF_PROVIDER }}",
            "GCP_DEPLOY_SERVICE_ACCOUNT: ${{ vars.GCP_DEPLOY_SERVICE_ACCOUNT }}",
            "uses: google-github-actions/auth@",
            "token_format: access_token",
            "access_token_lifetime: 300s",
            "create_credentials_file: false",
            "export_environment_variables: false",
            "WIF_ACCESS_TOKEN: ${{ steps.gcp-auth.outputs.access_token }}",
            '[[ -n "${WIF_ACCESS_TOKEN}" ]] ||',
            "Confirm WIF token exchange",
        ],
    )
    _assert_contains_none(
        identity_block,
        [
            "actions/checkout@",
            "setup-gcloud",
            "gcloud auth print-access-token",
            'echo "${WIF_ACCESS_TOKEN}"',
            "GITHUB_STEP_SUMMARY",
            "GITHUB_OUTPUT",
            "secrets.",
            "CLOUD_RUN_ENV_FILE_BASE64",
            "npm ",
            "pip install",
            "make release-cloud-run",
            "promote_cloud_run_revision",
            "deploy_firebase_hosting.py",
            "firebase deploy",
            "traffic",
        ],
    )

    guard_start = yml.index("  authorize-deploy-cutover:")
    deploy_start = yml.index("  deploy:", guard_start)
    guard_block = yml[guard_start:deploy_start]
    _assert_contains_all(
        guard_block,
        [
            "if [[ \"${PRODUCTION_DEPLOY_ENABLED:-}\" != \"true\" ]]; then",
            "::error::",
            "exit 1",
        ],
    )


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
    deploy = yml[yml.index("  deploy:"):]

    _assert_contains_all(
        yml,
        [
            "uses: google-github-actions/auth@",
            "GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}",
            "GCP_DEPLOY_WIF_PROVIDER: ${{ vars.GCP_DEPLOY_WIF_PROVIDER }}",
            "GCP_DEPLOY_SERVICE_ACCOUNT: ${{ vars.GCP_DEPLOY_SERVICE_ACCOUNT }}",
            "project_id: ${{ env.GCP_PROJECT_ID }}",
            "workload_identity_provider: ${{ env.GCP_DEPLOY_WIF_PROVIDER }}",
            "service_account: ${{ env.GCP_DEPLOY_SERVICE_ACCOUNT }}",
            "create_credentials_file: true",
            "export_environment_variables: true",
            "cleanup_credentials: true",
            "python scripts/deploy_firebase_hosting.py",
            "--site \"${FIREBASE_PROJECT_ID}\"",
            "npm --prefix ./apps/frontend run build",
            "TOOL=gcloud",
        ],
    )
    _assert_contains_none(
        deploy,
        [
            "FIREBASE_TOKEN",
            "GCP_SA_KEY",
            "credentials_json",
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
            "uses: google-github-actions/auth@",
            "GCP_PROJECT_ID: ${{ vars.GCP_PROJECT_ID }}",
            "GCP_PREFLIGHT_WIF_PROVIDER: ${{ vars.GCP_PREFLIGHT_WIF_PROVIDER }}",
            "GCP_PREFLIGHT_SERVICE_ACCOUNT: ${{ vars.GCP_PREFLIGHT_SERVICE_ACCOUNT }}",
            "project_id: ${{ env.GCP_PROJECT_ID }}",
            "workload_identity_provider: ${{ env.GCP_PREFLIGHT_WIF_PROVIDER }}",
            "service_account: ${{ env.GCP_PREFLIGHT_SERVICE_ACCOUNT }}",
            "create_credentials_file: true",
            "export_environment_variables: true",
            "cleanup_credentials: true",
            "scripts/deploy_firebase_hosting.py",
        ],
    )
    _assert_contains_none(
        yml,
        [
            "GCP_SA_KEY",
            "credentials_json",
            "environment: production",
            "firebase deploy --only hosting",
            "pageSize=1",
        ],
    )


def test_wif_permissions_are_scoped_and_normal_ci_has_no_oidc_token() -> None:
    """Only authenticated production jobs receive OIDC token minting permission."""
    deploy_workflow = yaml.safe_load(_read_text(".github/workflows/deploy-production.yml"))
    preflight_workflow = yaml.safe_load(_read_text(".github/workflows/production-deploy-preflight.yml"))
    ci_workflow = yaml.safe_load(_read_text(".github/workflows/ci.yml"))

    assert deploy_workflow["permissions"] == {"contents": "read", "actions": "read"}
    assert _read_workflow_job(".github/workflows/deploy-production.yml", "verify-target")["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert _read_workflow_job(".github/workflows/deploy-production.yml", "deploy")["permissions"] == {
        "contents": "read",
        "id-token": "write",
    }
    assert preflight_workflow["permissions"] == {"contents": "read"}
    assert _read_workflow_job(
        ".github/workflows/production-deploy-preflight.yml",
        "authenticated_read_only_probe",
    )["permissions"] == {"contents": "read", "id-token": "write"}
    assert _read_workflow_job(
        ".github/workflows/deploy-production.yml",
        "verify-deploy-identity",
    )["permissions"] == {"id-token": "write"}
    assert _read_workflow_job(
        ".github/workflows/deploy-production.yml",
        "authorize-deploy-cutover",
    )["permissions"] == {"contents": "read"}

    ci_jobs = ci_workflow["jobs"]
    assert all("id-token" not in job.get("permissions", {}) for job in ci_jobs.values())


def test_production_workflows_are_key_free() -> None:
    """Both production workflows must use WIF inputs with no legacy key fallback."""
    for path in (
        ".github/workflows/deploy-production.yml",
        ".github/workflows/production-deploy-preflight.yml",
    ):
        workflow = _read_text(path)
        _assert_contains_none(workflow, ["GCP_SA_KEY", "GCP_SA_PROJECT_ID", "credentials_json"])
        _assert_contains_all(
            workflow,
            [
                "project_id:",
                "workload_identity_provider:",
                "service_account:",
                "create_credentials_file: true",
                "export_environment_variables: true",
                "cleanup_credentials: true",
            ],
        )


def test_deploy_auth_starts_after_dependency_install_and_before_gcloud_setup() -> None:
    """Keep short-lived Google credentials out of dependency installation steps."""
    workflow = _read_text(".github/workflows/deploy-production.yml")
    deploy = workflow[workflow.index("  deploy:"):]
    frontend_install = deploy.index("Install frontend dependencies")
    frontend_build = deploy.index("Build frontend artifact")
    python_install = deploy.index("Install Python dependencies")
    materialize = deploy.index("Materialize production env file")
    validate = deploy.index("Validate deployment inputs")
    authenticate = deploy.index("Authenticate to Google Cloud with Workload Identity Federation")
    gcloud_setup = deploy.index("Set up gcloud SDK")
    hosting = deploy.index("Deploy Firebase Hosting")

    assert frontend_install < frontend_build < python_install < materialize < validate < authenticate < gcloud_setup
    hosting_block = deploy[hosting:]
    assert "npm --prefix ./apps/frontend run build" not in hosting_block


def test_cloud_build_service_account_is_explicit_and_deploy_scoped() -> None:
    """Only the authenticated deploy job may consume the dedicated build SA variable."""
    deploy_path = ".github/workflows/deploy-production.yml"
    deploy_workflow = yaml.safe_load(_read_text(deploy_path))
    deploy_job = _read_workflow_job(deploy_path, "deploy")
    identity_job = _read_workflow_job(deploy_path, "verify-deploy-identity")
    preflight_workflow = yaml.safe_load(_read_text(".github/workflows/production-deploy-preflight.yml"))
    ci_workflow = yaml.safe_load(_read_text(".github/workflows/ci.yml"))

    assert deploy_job["env"]["GCP_BUILD_SERVICE_ACCOUNT"] == "${{ vars.GCP_BUILD_SERVICE_ACCOUNT }}"
    assert "GCP_BUILD_SERVICE_ACCOUNT" not in identity_job.get("env", {})
    assert all("GCP_BUILD_SERVICE_ACCOUNT" not in job.get("env", {}) for job in preflight_workflow["jobs"].values())
    assert all("GCP_BUILD_SERVICE_ACCOUNT" not in job.get("env", {}) for job in ci_workflow["jobs"].values())

    deploy_text = _read_text(deploy_path)
    deploy_start = deploy_text.index("  deploy:")
    deploy_block = deploy_text[deploy_start:]
    assert 'BUILD_SERVICE_ACCOUNT="${GCP_BUILD_SERVICE_ACCOUNT}"' in deploy_block
    assert "GCP_BUILD_SERVICE_ACCOUNT is not set" in deploy_block
    assert "GCP_BUILD_SERVICE_ACCOUNT must be a service-account email in GCP_PROJECT_ID's project." in deploy_block
    assert r"@${GCP_PROJECT_ID}\.iam\.gserviceaccount\.com" in deploy_block
    assert "--build-service-account" not in _read_text(".github/workflows/production-deploy-preflight.yml")


def test_external_step_actions_are_full_sha_pinned_and_version_documented() -> None:
    violations: list[str] = []
    for path in sorted(Path(".github/workflows").glob("*.y*ml")):
        violations.extend(
            f"{path}: {violation}"
            for violation in _external_action_pin_violations(
                path.read_text(encoding="utf-8")
            )
        )
    assert not violations, "\n".join(violations)


def test_action_pin_contract_ignores_local_docker_container_reusable_and_run_text() -> None:
    workflow = """
name: synthetic
'on': workflow_dispatch
jobs:
  reusable:
    uses: acme/workflows/.github/workflows/reusable.yml@main
  local-reusable:
    uses: ./.github/workflows/reusable.yml
  build:
    container: ubuntu:24.04
    services:
      database:
        image: postgres:16
    steps:
      - uses: ./local-action
      - uses: ../local-action
      - uses: docker://alpine:3.20
      - run: |
          uses: example/fake-action@main
      - uses: example/action@main
      - uses: example/pinned-action@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # v4
        with:
          uses: example/input-value@main
"""

    violations = _external_action_pin_violations(workflow)
    assert len(violations) == 2
    assert all("example/action@main" in violation for violation in violations)


def test_action_pin_contract_accepts_lowercase_sha_and_short_or_full_version_comment() -> None:
    workflow = """
name: synthetic
'on': workflow_dispatch
jobs:
  build:
    steps:
      - uses: example/action@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa # v4
      - uses: example/other@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb # v5.0.0
"""

    assert _external_action_pin_violations(workflow) == []


def test_action_pin_contract_rejects_tags_short_long_uppercase_and_missing_comments() -> None:
    short_sha = "a" * 39
    long_sha = "b" * 41
    uppercase_sha = "A" * 40
    valid_sha = "c" * 40
    workflow = f"""
name: synthetic
'on': workflow_dispatch
jobs:
  build:
    steps:
      - uses: example/tag@v4 # v4
      - uses: example/short@{short_sha} # v4
      - uses: example/long@{long_sha} # v4
      - uses: example/uppercase@{uppercase_sha} # v4
      - uses: example/no-comment@{valid_sha}
"""

    violations = _external_action_pin_violations(workflow)
    assert len(violations) == 5
    assert sum("full lowercase SHA required" in violation for violation in violations) == 4
    assert sum("inline version comment required" in violation for violation in violations) == 1
    for reference in (
        "example/tag@v4",
        f"example/short@{short_sha}",
        f"example/long@{long_sha}",
        f"example/uppercase@{uppercase_sha}",
        f"example/no-comment@{valid_sha}",
    ):
        assert any(reference in violation for violation in violations)


def test_action_pin_contract_fails_closed_for_unknown_step_references() -> None:
    workflow = """
name: synthetic
'on': workflow_dispatch
jobs:
  build:
    steps:
      - uses: example/action
      - uses: https://example.test/action@main
      - uses: example/reusable/.github/workflows/reuse.yml@main
      - uses: ${{ inputs.action }}
      - uses: [example, action]
"""

    violations = _external_action_pin_violations(workflow)
    assert len(violations) == 5
    assert all(
        "unsupported step-level uses reference" in violation
        for violation in violations
    )


def test_all_workflow_yaml_files_parse() -> None:
    workflows = sorted(Path(".github/workflows").glob("*.y*ml"))
    assert workflows
    for path in workflows:
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None
