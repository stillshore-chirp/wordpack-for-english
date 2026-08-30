from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/scheduled-maintenance.yml"
REMOVED_WORKFLOWS = (
    ".github/workflows/codeql.yml",
    ".github/workflows/openssf-scorecard.yml",
    ".github/workflows/perf-backend.yml",
    ".github/workflows/playwright-nightly.yml",
)
JOBS = {
    "codeql": "codeql",
    "scorecard": "scorecard",
    "backend_performance": "backend-performance",
    "playwright": "playwright",
}


def _job_block(workflow: str, job_id: str) -> str:
    match = re.search(
        rf"^  {re.escape(job_id)}:\n(?P<body>.*?)(?=^  [a-zA-Z0-9_-]+:\n|\Z)",
        workflow,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"missing job: {job_id}"
    return match.group("body")


def test_scheduled_maintenance_contract():
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "  schedule:\n" in workflow
    assert '    - cron: "0 3 * * 1"' in workflow
    assert "  workflow_dispatch:\n" in workflow
    assert "      suite:\n" in workflow
    for option in ("all", "codeql", "scorecard", "backend-performance", "playwright"):
        assert f"          - {option}\n" in workflow
    assert "pull_request:" not in workflow
    assert "push:" not in workflow
    assert "workflow_run:" not in workflow
    assert re.search(r"^permissions:\n  contents: read\n\njobs:\n", workflow, re.MULTILINE)

    for job_id, suite in JOBS.items():
        block = _job_block(workflow, job_id)
        assert (
            f"if: ${{{{ github.event_name == 'schedule' || inputs.suite == 'all' || "
            f"inputs.suite == '{suite}' }}}}"
        ) in block
        assert "needs:" not in block
        assert "security-events:" not in block or job_id in {"codeql", "scorecard"}
        assert "id-token:" not in block or job_id == "scorecard"

    names = re.findall(r"^    name: (.+)$", workflow, re.MULTILINE)
    assert len(set(names)) == 4

    codeql = _job_block(workflow, "codeql")
    assert "security-events: write" in codeql
    assert "github/codeql-action/init@v4" in codeql
    assert "github/codeql-action/analyze@v4" in codeql
    assert "queries: +security-extended,security-and-quality" in codeql
    assert "javascript-typescript" in codeql and "python" in codeql

    scorecard = _job_block(workflow, "scorecard")
    assert "actions: read" in scorecard
    assert "security-events: write" in scorecard
    assert "id-token: write" in scorecard
    assert "ossf/scorecard-action@v2.4.3" in scorecard
    assert "results_file: scorecard-results.sarif" in scorecard
    assert "results_format: sarif" in scorecard
    assert "retention-days: 30" in scorecard

    performance = _job_block(workflow, "backend_performance")
    assert 'API_P95_THRESHOLD_MS: "2000"' in performance
    assert "python-version: ['3.14']" in performance
    assert "pip install -r requirements.txt" in performance
    assert "pytest -q --no-cov tests/test_api_performance.py" in performance
    assert "security-events:" not in performance
    assert "id-token:" not in performance

    playwright = _job_block(workflow, "playwright")
    assert "npx playwright install --with-deps" in playwright
    assert "npx playwright test -c tests/e2e/playwright.config.ts --browser=chromium" in playwright
    assert "if: ${{ failure() }}" in playwright
    assert "retention-days: 14" in playwright
    assert "playwright-report/" in playwright and "test-results/" in playwright
    assert "security-events:" not in playwright
    assert "id-token:" not in playwright

    for path in REMOVED_WORKFLOWS:
        assert not (ROOT / path).exists(), f"obsolete workflow remains: {path}"
