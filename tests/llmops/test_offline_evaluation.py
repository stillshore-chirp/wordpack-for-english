from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.evaluators.contracts import evaluate_fixture
from scripts.llmops.estimate_run import estimate
from scripts.llmops.offline_report import build_report, render_markdown


def test_required_wordpack_and_five_category_fixture_passes_without_network() -> None:
    result = evaluate_fixture(Path("evals/fixtures/wordpack_converge.json"))
    assert result["passed"] is True, result["findings"]


def test_offline_report_generates_json_and_short_markdown_summary() -> None:
    report = build_report(Path("evals/fixtures"))
    markdown = render_markdown(report)
    json.dumps(report)
    assert report["offline_contract_tests"] == "Passed"
    assert report["fixture_regressions"] == 0
    assert "Paid LLM requests: 0" in markdown


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
