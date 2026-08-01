from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))

from backend.flows.quiz_generate import QuizGenerateFlow
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
                                    "wrong_choice_explanations_ja": {},
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
