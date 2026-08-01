from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from evals.evaluators.contracts import evaluate_fixture, evaluate_wordpack_payload
from backend.config import settings
from backend.domain.quiz.prompt_policy import build_quiz_generation_prompt
from backend.infrastructure.llm.generated_contracts import (
    GeneratedQuizPayload,
    GeneratedWordPackPayload,
)
from backend.infrastructure.llm.prompts.examples import (
    build_examples_prompt,
    examples_response_schema,
)
from backend.infrastructure.llm.prompts.wordpack import build_wordpack_prompt
from backend.infrastructure.llm.wordpack_generator import build_llm_info
from backend.llmops.identity import prompt_identity_from_builder
from scripts.llmops.estimate_run import estimate
from scripts.llmops.offline_report import (
    PRODUCTION_EXAMPLE_CATEGORIES,
    build_report,
    current_snapshot,
    render_markdown,
)
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


def test_evaluator_fails_when_provenance_records_application_failure() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    payload["generation_provenance"][0]["validation"]["application"] = False

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert any(finding["code"] == "application_failure" for finding in findings)


def test_evaluator_requires_model_in_provenance_when_expected() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    provenance = payload["generation_provenance"][0]
    provenance.pop("requested_model")

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert any(finding["code"] == "model_missing" for finding in findings)


def test_evaluator_compares_expected_model_with_requested_model() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    payload["generation_provenance"][0]["resolved_model"] = "gpt-5.6-luna-2026-07-31"

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert not any(finding["code"] == "model_mismatch" for finding in findings)


def test_evaluator_rejects_provenance_from_another_operation() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    payload["generation_provenance"][0]["operation"] = "unrelated.operation"
    payload["examples"]["Dev"][0]["generation_provenance"][0]["operation"] = (
        "unrelated.operation"
    )

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    mismatches = [
        finding for finding in findings if finding["code"] == "operation_mismatch"
    ]
    assert {finding["operation"] for finding in mismatches} == {
        "wordpack",
        "examples.Dev",
    }


def test_evaluator_rejects_a_wordpack_with_an_unexpected_lemma() -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    payload["lemma"] = "diverge"

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert any(finding["code"] == "lemma_mismatch" for finding in findings)


@pytest.mark.parametrize(
    ("validation", "expected_code"),
    [
        (None, "validation_missing"),
        ("invalid", "validation_invalid"),
        ({"parse": True, "schema": True}, "validation_outcome_missing"),
        (
            {"parse": None, "schema": None, "application": None},
            "validation_outcome_invalid",
        ),
    ],
)
def test_evaluator_requires_all_validation_outcomes(
    validation: object,
    expected_code: str,
) -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    payload = fixture["wordpack"]
    provenance = payload["generation_provenance"][0]
    if validation is None:
        provenance.pop("validation")
    else:
        provenance["validation"] = validation

    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma="converge",
        expected_model="gpt-5.6-luna",
        expected_examples_per_category=2,
    )

    assert any(finding["code"] == expected_code for finding in findings)


def test_live_identity_settings_match_production_defaults() -> None:
    production = build_llm_info({})

    assert live_eval._live_major_settings(settings.llm_model) == production
    assert live_eval._live_major_settings(
        settings.llm_model,
        category="Dev",
        count=2,
    ) == {**production, "category": "Dev", "count": 2}


def test_live_application_rejects_blank_glosses() -> None:
    class GeneratedSense:
        gloss_ja = "   "

    assert live_eval._has_usable_senses([GeneratedSense()]) is False


def test_live_examples_apply_production_truncation_before_usability_check() -> None:
    rows = [
        {"en": " first ", "ja": " 最初 ", "grammar_ja": " "},
        {"en": "second", "ja": "2番目"},
        {"en": "third", "ja": "3番目"},
    ]

    retained = live_eval._retained_example_rows(rows, 2)

    assert retained == [
        {"en": "first", "ja": "最初", "grammar_ja": None},
        {"en": "second", "ja": "2番目", "grammar_ja": None},
    ]


def test_live_wordpack_classifies_non_object_json_as_parsed_but_schema_invalid() -> None:
    payload, parse_ok, schema_ok, generated = live_eval._parse_wordpack_completion(
        "[]",
        parser=json.loads,
        payload_model=GeneratedWordPackPayload,
    )

    assert payload == {}
    assert parse_ok is True
    assert schema_ok is False
    assert generated is None


def test_offline_report_generates_json_and_short_markdown_summary() -> None:
    report = build_report(Path("evals/fixtures"))
    markdown = render_markdown(report)
    json.dumps(report)
    assert report["offline_contract_tests"] == "Passed"
    assert report["fixture_regressions"] == 0
    assert report["baseline_status"] == "Passed"
    assert report["missing_required_cases"] == []
    assert "Paid LLM requests: 0" in markdown


def test_offline_snapshot_matches_production_prompt_identities() -> None:
    llm_info = build_llm_info({})
    expected = {
        "wordpack.core": prompt_identity_from_builder(
            prompt_id="wordpack.core",
            operation="wordpack.generate",
            builder=build_wordpack_prompt,
            schema=GeneratedWordPackPayload.model_json_schema(),
            major_settings=llm_info,
        ).prompt_revision,
        "quiz.generate": prompt_identity_from_builder(
            prompt_id="quiz.generate",
            operation="quiz.generate",
            builder=build_quiz_generation_prompt,
            schema=GeneratedQuizPayload.model_json_schema(),
            major_settings=llm_info,
        ).prompt_revision,
    }
    for category in PRODUCTION_EXAMPLE_CATEGORIES:
        identity_name = f"wordpack.examples.{category.value.lower()}"
        expected[identity_name] = prompt_identity_from_builder(
            prompt_id=identity_name,
            operation=identity_name,
            builder=build_examples_prompt,
            schema=examples_response_schema(),
            major_settings={
                **llm_info,
                "category": category.value,
                "count": 2,
            },
        ).prompt_revision

    assert current_snapshot()["prompt_revisions"] == expected


def test_offline_report_fails_when_required_fixture_is_replaced(
    tmp_path: Path,
) -> None:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    fixture["case_id"] = "replacement-passing-case"
    fixtures_dir = tmp_path / "fixtures"
    fixtures_dir.mkdir()
    (fixtures_dir / "replacement.json").write_text(
        json.dumps(fixture, ensure_ascii=False),
        encoding="utf-8",
    )

    report = build_report(fixtures_dir)

    assert report["offline_contract_tests"] == "Failed"
    assert report["fixture_regressions"] == 1
    assert report["missing_required_cases"] == ["wordpack-converge-contract-v1"]


@pytest.mark.parametrize("baseline_contents", [None, "not-json", "[]", "{}"])
def test_offline_report_fails_when_baseline_cannot_be_loaded(
    tmp_path: Path,
    baseline_contents: str | None,
) -> None:
    baseline_path = tmp_path / "offline-summary.json"
    if baseline_contents is not None:
        baseline_path.write_text(baseline_contents, encoding="utf-8")

    report = build_report(
        Path("evals/fixtures"),
        baseline_path=baseline_path,
    )

    assert report["offline_contract_tests"] == "Failed"
    assert report["fixture_regressions"] == 1
    assert report["baseline_status"] == "Failed"


def test_llmops_clis_start_without_application_session_secret(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    clean_env = os.environ.copy()
    clean_env.pop("SESSION_SECRET_KEY", None)
    clean_env["PYTHONPATH"] = os.pathsep.join(
        (str(repository_root), str(repository_root / "apps" / "backend"))
    )
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
        cwd=repository_root,
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
        cwd=repository_root,
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


def test_live_estimate_rejects_an_empty_case_set(tmp_path: Path) -> None:
    cases_file = tmp_path / "empty-cases.json"
    cases_file.write_text('{"cases": []}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="at least one case"):
        estimate(
            cases_file,
            max_cases=1,
            max_requests=6,
            max_output_tokens=25000,
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
