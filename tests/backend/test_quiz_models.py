from __future__ import annotations

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))

from backend.application.quiz.scoring import score_quiz_attempt
from backend.models.quiz import Quiz, QuizAnswerInput, QuizGenerateRequest, QuizQuestion


def _question(question_id: str, correct_choice_id: str = "A") -> dict:
    return {
        "id": question_id,
        "order": 1,
        "type": "detail",
        "prompt": "What reduces latency?",
        "choices": [
            {"id": "A", "text": "A fallback"},
            {"id": "B", "text": "A redesign"},
            {"id": "C", "text": "A delay"},
            {"id": "D", "text": "A meeting"},
        ],
        "correct_choice_id": correct_choice_id,
        "explanation": {
            "explanation_ja": "本文に fallback とあります。",
            "evidence_passage_id": "p1",
            "evidence_text": "adding a fallback",
            "evidence_start": 27,
            "evidence_end": 44,
            "wrong_choice_explanations_ja": {"B": "本文にありません。"},
            "related_lemmas": ["fallback"],
        },
    }


def _quiz() -> Quiz:
    return Quiz.model_validate(
        {
            "id": "quiz:test",
            "title_en": "Reliable API Deployments",
            "format_profile": "single_passage",
            "generation_domain": "technical",
            "domain_intensity": "standard",
            "difficulty": "medium",
            "passages": [
                {
                    "id": "p1",
                    "order": 1,
                    "kind": "article",
                    "title": "Deployment review",
                    "body_en": "Teams mitigate latency by adding a fallback.",
                    "body_ja": "チームはフォールバックを追加してレイテンシを軽減する。",
                    "speaker_labels": [],
                }
            ],
            "sections": [
                {
                    "id": "s1",
                    "order": 1,
                    "title": "Reading",
                    "description_ja": "本文理解",
                    "passage_ids": ["p1"],
                    "questions": [_question("q1"), _question("q2", "B")],
                }
            ],
            "related_word_packs": [],
            "source_word_pack_ids": [],
            "source_lemmas": ["mitigate", "latency"],
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
    )


def test_quiz_question_requires_unique_choice_ids() -> None:
    payload = _question("q1")
    payload["choices"][-1]["id"] = "C"

    with pytest.raises(ValidationError):
        QuizQuestion.model_validate(payload)


def test_quiz_rejects_unknown_passage_reference() -> None:
    payload = _quiz().model_dump(mode="json")
    payload["sections"][0]["passage_ids"] = ["missing"]

    with pytest.raises(ValidationError):
        Quiz.model_validate(payload)


def test_quiz_generate_request_normalizes_sources() -> None:
    req = QuizGenerateRequest.model_validate(
        {
            "word_pack_ids": ["wp:mitigate"],
            "lemmas": ["Latency", " latency "],
            "avoid_topics": [" malware ", "malware", ""],
            "model": "gpt-5.6-luna",
        }
    )

    assert req.lemmas == ["Latency"]
    assert req.avoid_topics == ["malware"]


def test_quiz_generate_request_requires_sources() -> None:
    with pytest.raises(ValidationError):
        QuizGenerateRequest.model_validate({"lemmas": [], "word_pack_ids": []})


def test_score_quiz_attempt_scores_unanswered_as_incorrect() -> None:
    quiz = _quiz()
    score, total, results = score_quiz_attempt(
        quiz,
        [QuizAnswerInput(question_id="q1", selected_choice_id="A")],
    )

    assert score == 1
    assert total == 2
    assert [result.is_correct for result in results] == [True, False]
    assert results[1].selected_choice_id is None
