from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))

from backend.flows import quiz_generate as quiz_module
from backend.flows.quiz_generate import QuizGenerateFlow, QuizGenerationProgress
from backend.llmops.completion import generation_workflow_context
from backend.models.quiz import QuizGenerateRequest


class FakeQuizStore:
    def __init__(self) -> None:
        self.saved: dict[str, Any] | None = None

    def get_word_pack(self, word_pack_id: str):
        if word_pack_id == "wp:mitigate":
            return ("mitigate", "{}", "2024-01-01T00:00:00+00:00", "2024-01-01T00:00:00+00:00")
        return None

    def get_word_pack_metadata(self, word_pack_id: str) -> dict[str, Any]:
        return {"examples_category_counts": {"Dev": 1}}

    def find_word_pack_id_by_lemma(self, lemma: str) -> str | None:
        return "wp:latency" if lemma.lower() == "latency" else None

    def save_quiz(self, quiz_id: str, payload: dict[str, Any], related_word_packs: list[dict[str, Any]]) -> None:
        self.saved = {**payload, "id": quiz_id, "related_word_packs": related_word_packs}

    def get_quiz(self, quiz_id: str) -> dict[str, Any] | None:
        return self.saved


class FakeQuizLlm:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return json.dumps(
            {
                "title_en": "Latency Review",
                "format_profile": "single_passage",
                "generation_domain": "technical",
                "domain_intensity": "standard",
                "difficulty": "medium",
                "passages": [
                    {
                        "id": "p1",
                        "order": 1,
                        "kind": "article",
                        "title": "Review",
                        "body_en": "The team studied latency before the release.",
                        "body_ja": "チームはリリース前にレイテンシを調査した。",
                        "speaker_labels": [],
                    }
                ],
                "notes_ja": "本文根拠を確認します。",
                "sections": [
                    {
                        "id": "s1",
                        "order": 1,
                        "title": "Reading",
                        "description_ja": "本文理解",
                        "passage_ids": ["p1"],
                        "questions": [
                            {
                                "id": "q1",
                                "order": 1,
                                "type": "detail",
                                "prompt": "What did the team study?",
                                "choices": [
                                    {"id": "A", "text": "Latency"},
                                    {"id": "B", "text": "Billing"},
                                    {"id": "C", "text": "Hiring"},
                                    {"id": "D", "text": "Training"},
                                ],
                                "correct_choice_id": "A",
                                "explanation": {
                                    "explanation_ja": "本文に latency とあります。",
                                    "evidence_passage_id": "p1",
                                    "evidence_text": "studied latency",
                                    "evidence_start": 9,
                                    "evidence_end": 24,
                                    "wrong_choice_explanations_ja": {
                                        "B": "本文に根拠がありません。",
                                        "C": "本文に根拠がありません。",
                                        "D": "本文に根拠がありません。",
                                    },
                                    "related_lemmas": ["latency"],
                                },
                            }
                        ],
                    }
                ],
                "related_lemmas": ["latency"],
            },
            ensure_ascii=False,
        )


def test_quiz_generate_flow_warns_when_source_lemma_is_not_in_passage() -> None:
    store = FakeQuizStore()
    req = QuizGenerateRequest.model_validate(
        {
            "word_pack_ids": ["wp:mitigate"],
            "lemmas": ["latency"],
            "format_profile": "single_passage",
            "generation_domain": "technical",
            "domain_intensity": "standard",
            "difficulty": "medium",
            "section_count": 1,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )

    llm = FakeQuizLlm()
    quiz = QuizGenerateFlow(store=store, llm=llm).run(req)

    links = {link.lemma: link for link in quiz.related_word_packs}
    assert links["latency"].word_pack_id == "wp:latency"
    assert links["latency"].occurrences
    assert links["mitigate"].warning is not None
    assert "本文中に見つかりません" in links["mitigate"].warning
    assert llm.calls == 1
    assert len(quiz.generation_provenance) == 1


def test_quiz_generate_flow_rejects_requested_size_mismatch() -> None:
    store = FakeQuizStore()
    req = QuizGenerateRequest.model_validate(
        {
            "lemmas": ["latency"],
            "section_count": 2,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )

    with pytest.raises(RuntimeError, match="QUIZ_APPLICATION_INVALID"):
        QuizGenerateFlow(store=store, llm=FakeQuizLlm()).run(req)

    assert store.saved is None


def test_quiz_generate_flow_rejects_incomplete_wrong_choice_explanations() -> None:
    payload = json.loads(FakeQuizLlm().complete(""))
    payload["sections"][0]["questions"][0]["explanation"][
        "wrong_choice_explanations_ja"
    ] = {"B": "本文に根拠がありません。"}

    class IncompleteExplanationLlm:
        def complete(self, _prompt: str) -> str:
            return json.dumps(payload, ensure_ascii=False)

    req = QuizGenerateRequest.model_validate(
        {
            "lemmas": ["latency"],
            "section_count": 1,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )

    with pytest.raises(RuntimeError, match="QUIZ_APPLICATION_INVALID"):
        QuizGenerateFlow(
            store=FakeQuizStore(),
            llm=IncompleteExplanationLlm(),
        ).run(req)


@pytest.mark.parametrize(
    "blank_field",
    [
        "title_en",
        "passage.body_en",
        "section.title",
        "question.prompt",
        "choice.text",
        "explanation.explanation_ja",
        "explanation.wrong_choice",
    ],
)
def test_quiz_generate_flow_rejects_whitespace_only_required_text(
    blank_field: str,
) -> None:
    payload = json.loads(FakeQuizLlm().complete(""))
    question = payload["sections"][0]["questions"][0]
    if blank_field == "title_en":
        payload["title_en"] = "   "
    elif blank_field == "passage.body_en":
        payload["passages"][0]["body_en"] = "   "
    elif blank_field == "section.title":
        payload["sections"][0]["title"] = "   "
    elif blank_field == "question.prompt":
        question["prompt"] = "   "
    elif blank_field == "choice.text":
        question["choices"][0]["text"] = "   "
    elif blank_field == "explanation.explanation_ja":
        question["explanation"]["explanation_ja"] = "   "
    elif blank_field == "explanation.wrong_choice":
        question["explanation"]["wrong_choice_explanations_ja"]["B"] = "   "

    class BlankTextQuizLlm:
        def complete(self, _prompt: str) -> str:
            return json.dumps(payload, ensure_ascii=False)

    req = QuizGenerateRequest.model_validate(
        {
            "lemmas": ["latency"],
            "section_count": 1,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )
    store = FakeQuizStore()

    with pytest.raises(RuntimeError, match="QUIZ_APPLICATION_INVALID"):
        QuizGenerateFlow(store=store, llm=BlankTextQuizLlm()).run(req)

    assert store.saved is None


def test_quiz_repair_records_complete_boolean_validation_outcomes() -> None:
    valid_payload = FakeQuizLlm().complete("")

    class RepairingQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _prompt: str) -> str:
            self.calls += 1
            return "not-json" if self.calls == 1 else valid_payload

    req = QuizGenerateRequest.model_validate(
        {
            "lemmas": ["latency"],
            "section_count": 1,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )

    quiz = QuizGenerateFlow(
        store=FakeQuizStore(),
        llm=RepairingQuizLlm(),
    ).run(req)

    assert [entry["validation"] for entry in quiz.generation_provenance] == [
        {"parse": True, "schema": True, "application": True},
    ]


def _alignment_mismatch_payload() -> str:
    payload = json.loads(FakeQuizLlm().complete(""))
    payload["passages"][0]["body_en"] = "The first sentence ends. The second sentence ends."
    payload["passages"][0]["body_ja"] = "二つの英文を一つの日本語文にまとめた。"
    return json.dumps(payload, ensure_ascii=False)


def _single_question_request() -> QuizGenerateRequest:
    return QuizGenerateRequest.model_validate(
        {
            "lemmas": ["latency"],
            "section_count": 1,
            "questions_per_section": 1,
        }
    )


def test_quiz_alignment_retry_regenerates_the_whole_quiz_and_then_succeeds() -> None:
    valid_payload = FakeQuizLlm().complete("")

    class RetryingQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, prompt: str) -> str:
            self.calls += 1
            assert "previous" not in prompt.lower()
            return _alignment_mismatch_payload() if self.calls == 1 else valid_payload

    progress: list[QuizGenerationProgress] = []
    llm = RetryingQuizLlm()
    store = FakeQuizStore()
    req = _single_question_request()

    quiz = QuizGenerateFlow(store=store, llm=llm).run(req, progress.append)

    assert quiz.title_en == "Latency Review"
    assert quiz.translation_alignment_version == "deterministic_v1"
    assert llm.calls == 2
    assert [(item.attempt_count, item.retry_phase) for item in progress] == [
        (1, "generation"),
        (2, "translation_alignment"),
    ]
    assert store.saved is not None
    assert len(quiz.generation_provenance) == 1


def test_quiz_alignment_retry_stops_after_five_total_calls_without_saving() -> None:
    class AlwaysMisalignedQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _prompt: str) -> str:
            self.calls += 1
            return _alignment_mismatch_payload()

    progress: list[QuizGenerationProgress] = []
    llm = AlwaysMisalignedQuizLlm()
    store = FakeQuizStore()
    req = _single_question_request()

    with pytest.raises(RuntimeError, match="QUIZ_TRANSLATION_ALIGNMENT_FAILED"):
        QuizGenerateFlow(store=store, llm=llm).run(req, progress.append)

    assert llm.calls == 5
    assert [item.attempt_count for item in progress] == [1, 2, 3, 4, 5]
    assert store.saved is None


def test_quiz_json_repair_and_alignment_retry_share_the_five_call_budget() -> None:
    valid_payload = FakeQuizLlm().complete("")

    class RepairThenRetryQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _prompt: str) -> str:
            self.calls += 1
            return {
                1: "not-json",
                2: _alignment_mismatch_payload(),
                3: valid_payload,
            }[self.calls]

    progress: list[QuizGenerationProgress] = []
    llm = RepairThenRetryQuizLlm()
    req = _single_question_request()

    QuizGenerateFlow(store=FakeQuizStore(), llm=llm).run(req, progress.append)

    assert llm.calls == 3
    assert [(item.attempt_count, item.retry_phase) for item in progress] == [
        (1, "generation"),
        (2, "json_repair"),
        (3, "translation_alignment"),
    ]


def test_quiz_does_not_start_a_sixth_json_repair_call() -> None:
    class InvalidOnFifthCallQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _prompt: str) -> str:
            self.calls += 1
            return "not-json" if self.calls == 5 else _alignment_mismatch_payload()

    llm = InvalidOnFifthCallQuizLlm()
    store = FakeQuizStore()
    req = _single_question_request()

    with pytest.raises(RuntimeError, match="QUIZ_JSON_PARSE_FAILED"):
        QuizGenerateFlow(store=store, llm=llm).run(req)

    assert llm.calls == 5
    assert store.saved is None


def test_quiz_provider_disables_internal_retry_to_enforce_physical_call_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = FakeQuizLlm()
    provider_options: dict[str, object] = {}

    def fake_get_llm_provider(**kwargs: object) -> FakeQuizLlm:
        provider_options.update(kwargs)
        return llm

    monkeypatch.setattr(quiz_module, "get_llm_provider", fake_get_llm_provider)
    req = _single_question_request()

    QuizGenerateFlow(store=FakeQuizStore()).run(req)

    assert provider_options["single_attempt"] is True


def test_quiz_alignment_observability_contains_counts_without_generated_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_text = "private-generated-alignment-content"
    payload = json.loads(_alignment_mismatch_payload())
    payload["passages"][0]["body_en"] = f"{sensitive_text}. Another sentence."

    class MisalignedThenValidQuizLlm:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, _prompt: str) -> str:
            self.calls += 1
            if self.calls == 1:
                return json.dumps(payload, ensure_ascii=False)
            return FakeQuizLlm().complete("")

    span_metadata: list[dict[str, object]] = []

    @contextmanager
    def capture_span(**kwargs: object):
        metadata = kwargs.get("metadata")
        if isinstance(metadata, dict):
            span_metadata.append(metadata)
        yield None

    monkeypatch.setattr(quiz_module, "span", capture_span)

    with generation_workflow_context("quiz-job:test-correlation"):
        QuizGenerateFlow(
            store=FakeQuizStore(),
            llm=MisalignedThenValidQuizLlm(),
        ).run(_single_question_request())

    serialized = json.dumps(span_metadata, ensure_ascii=False)
    assert sensitive_text not in serialized
    alignment = next(
        item for item in span_metadata if item.get("retry_reason") == "sentence_count_mismatch"
    )
    assert alignment["passage_index"] == 1
    assert alignment["paragraph_index"] == 1
    assert alignment["english_sentence_count"] == 2
    assert alignment["japanese_sentence_count"] == 1
    assert alignment["workflow_id"] == "quiz-job:test-correlation"
    assert any(item.get("final_success") is True for item in span_metadata)


def test_quiz_schema_failure_log_excludes_generated_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    valid_payload = json.loads(FakeQuizLlm().complete(""))
    sensitive_title = "private-generated-content-" * 10
    valid_payload["title_en"] = sensitive_title

    class InvalidQuizLlm:
        def complete(self, _prompt: str) -> str:
            return json.dumps(valid_payload, ensure_ascii=False)

    logged: list[tuple[str, dict[str, object]]] = []

    def capture(event: str, **values: object) -> None:
        logged.append((event, values))

    monkeypatch.setattr(quiz_module.logger, "warning", capture)
    req = QuizGenerateRequest.model_validate(
        {
            "word_pack_ids": ["wp:mitigate"],
            "lemmas": ["latency"],
            "format_profile": "single_passage",
            "generation_domain": "technical",
            "domain_intensity": "standard",
            "difficulty": "medium",
            "section_count": 1,
            "questions_per_section": 1,
            "model": "gpt-5.6-luna",
        }
    )

    with pytest.raises(RuntimeError, match="QUIZ_SCHEMA_INVALID"):
        QuizGenerateFlow(store=FakeQuizStore(), llm=InvalidQuizLlm()).run(req)

    event, values = next(
        item for item in logged if item[0] == "quiz_generated_schema_invalid"
    )
    serialized = json.dumps({"event": event, **values}, ensure_ascii=False)
    assert sensitive_title not in serialized
    assert "input_value" not in serialized
    assert values["error_type"] == "ValidationError"
    assert values["error_count"] == 1
    assert values["field_locations"] == ["title_en"]
