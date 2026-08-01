from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from evals.evaluators.contracts import evaluate_fixture, evaluate_wordpack_payload
from backend.config import settings
from scripts.llmops.estimate_run import estimate
from scripts.llmops.offline_report import build_report, render_markdown
from scripts.llmops import live_eval


def test_required_wordpack_and_five_category_fixture_passes_without_network() -> None:
    result = evaluate_fixture(Path("evals/fixtures/wordpack_converge.json"))
    assert result["passed"] is True, result["findings"]


def test_evaluator_fails_when_provenance_records_generated_schema_failure() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    payload["generation_provenance"][0]["validation"]["schema"] = False

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert any(finding["code"] == "schema_failure" for finding in findings)


def test_offline_report_generates_json_and_short_markdown_summary() -> None:
    report = build_report(Path("evals/fixtures"))
    markdown = render_markdown(report)
    json.dumps(report)
    assert report["offline_contract_tests"] == "Passed"
    assert report["fixture_regressions"] == 0
    assert "Paid LLM requests: 0" in markdown


def test_llmops_clis_start_without_application_session_secret(tmp_path: Path) -> None:
    clean_env = os.environ.copy()
    clean_env.pop("SESSION_SECRET_KEY", None)
    clean_env["PYTHONPATH"] = "apps/backend"
    import_check = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; import scripts.llmops.live_eval; "
                "assert len(os.environ['SESSION_SECRET_KEY']) >= 32"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert import_check.returncode == 0, import_check.stderr

    report = subprocess.run(
        [
            sys.executable,
            "scripts/llmops/offline_report.py",
            "--json-output",
            str(tmp_path / "report.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=clean_env,
    )
    assert report.returncode == 0, report.stderr
    assert (tmp_path / "report.json").is_file()


def test_live_estimate_has_zero_paid_requests_and_enforces_hard_limits() -> None:
    result = estimate(
        Path("evals/cases/live_smoke.json"),
        max_cases=1,
        max_requests=6,
        max_output_tokens=25000,
    )
    assert result == {
        "case_count": 1,
        "estimated_requests": 6,
        "max_output_tokens": 25000,
        "paid_llm_requests": 0,
    }
    with pytest.raises(ValueError, match="hard|between"):
        estimate(
            Path("evals/cases/live_smoke.json"),
            max_cases=6,
            max_requests=30,
            max_output_tokens=150000,
        )
    with pytest.raises(ValueError, match="cannot allocate"):
        estimate(
            Path("evals/cases/live_smoke.json"),
            max_cases=1,
            max_requests=6,
            max_output_tokens=5,
        )


def test_live_failure_persists_reserved_budget_and_failure_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailingProvider:
        def complete_result(self, *_args: object, **_kwargs: object) -> object:
            raise TimeoutError("provider timed out")

    output = tmp_path / "failed-live-report.json"
    monkeypatch.setattr(settings, "llm_max_tokens", settings.llm_max_tokens)
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "live_eval.py",
            "--mode",
            "live",
            "--confirm",
            live_eval.CONFIRM_PHRASE,
            "--max-cases",
            "1",
            "--max-requests",
            "6",
            "--max-output-tokens",
            "25000",
            "--output",
            str(output),
        ],
    )

    with pytest.raises(TimeoutError, match="provider timed out"):
        live_eval.main(provider_factory=lambda **_kwargs: FailingProvider())

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["paid_llm_requests"] == 1
    assert report["reserved_output_tokens"] > 0
    assert report["results"] == []
    assert report["failure"] == {
        "stage": "live_evaluation",
        "error_type": "TimeoutError",
    }
