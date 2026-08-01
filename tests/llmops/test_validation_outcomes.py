from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from backend.infrastructure.llm.generated_contracts import (
    GeneratedQuizPayload,
    GeneratedWordPackPayload,
)
from backend.llmops.validation import parse_article_lemmas, parse_category_lemma


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["resilience"]', (["resilience"], True, True)),
        ("[]", ([], True, True)),
        ('{"lemmas":["resilience"]}', (["resilience"], True, False)),
        ('{"lemmas":[]}', ([], True, False)),
        ("{}", ([], True, False)),
        ("not-json", ([], False, False)),
    ],
)
def test_article_lemma_validation_separates_parse_schema_and_application_value(
    raw: str, expected: tuple[list[str], bool, bool]
) -> None:
    assert parse_article_lemmas(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"lemma":"resilience"}', ("resilience", True, True)),
        ("{}", ("", True, False)),
        ('{"lemma":123}', ("", True, False)),
        ("not-json", ("", False, False)),
    ],
)
def test_category_lemma_validation_separates_parse_and_schema(
    raw: str, expected: tuple[str, bool, bool]
) -> None:
    assert parse_category_lemma(raw) == expected


def test_generated_contract_schemas_exclude_server_owned_fields() -> None:
    wordpack_fields = set(GeneratedWordPackPayload.model_fields)
    quiz_fields = set(GeneratedQuizPayload.model_fields)

    assert "senses" in wordpack_fields
    assert "lemma" not in wordpack_fields
    assert "generation_provenance" not in wordpack_fields
    assert "guest_public" not in wordpack_fields
    assert "checked_only_count" not in wordpack_fields
    assert "related_lemmas" in quiz_fields
    assert "id" not in quiz_fields
    assert "created_at" not in quiz_fields
    assert "generation_started_at" not in quiz_fields


def _complete_generated_wordpack_payload() -> dict[str, Any]:
    return {
        "senses": [
            {
                "id": "s1",
                "gloss_ja": "収束する",
                "definition_ja": "複数の対象が一点へ近づくことです。",
                "nuances_ja": "結果が一致する比喩的用法もあります。",
                "patterns": ["converge on"],
                "synonyms": ["meet"],
                "antonyms": ["diverge"],
                "register": "neutral",
                "notes_ja": "自動詞として使います。",
            }
        ],
        "sense_title": "一点へ収束する",
        "collocations": {
            "general": {
                "verb_object": [],
                "adj_noun": [],
                "prep_noun": [],
            },
            "academic": {
                "verb_object": [],
                "adj_noun": [],
                "prep_noun": [],
            },
        },
        "contrast": [],
        "etymology": {"note": "ラテン語に由来します。", "confidence": "medium"},
        "study_card": "複数のものが同じ地点へ近づく意味です。",
        "pronunciation": {"ipa_RP": "/kənˈvɜːdʒ/"},
    }


@pytest.mark.parametrize(
    "missing_path",
    [
        "sense.patterns",
        "sense.definition_ja",
        "collocations.general.verb_object",
        "collocations.academic",
        "etymology.confidence",
    ],
)
def test_generated_wordpack_contract_requires_prompt_nested_fields(
    missing_path: str,
) -> None:
    payload = deepcopy(_complete_generated_wordpack_payload())
    if missing_path == "sense.patterns":
        del payload["senses"][0]["patterns"]
    elif missing_path == "sense.definition_ja":
        del payload["senses"][0]["definition_ja"]
    elif missing_path == "collocations.general.verb_object":
        del payload["collocations"]["general"]["verb_object"]
    elif missing_path == "collocations.academic":
        del payload["collocations"]["academic"]
    elif missing_path == "etymology.confidence":
        del payload["etymology"]["confidence"]

    with pytest.raises(ValidationError):
        GeneratedWordPackPayload.model_validate(payload)


def test_generated_wordpack_contract_accepts_complete_prompt_shape() -> None:
    result = GeneratedWordPackPayload.model_validate(
        _complete_generated_wordpack_payload()
    )

    assert result.senses[0].patterns == ["converge on"]


def _complete_generated_quiz_payload() -> dict[str, Any]:
    return {
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
                "body_en": "The team studied latency before release.",
                "body_ja": "チームはリリース前にレイテンシを調査しました。",
                "speaker_labels": [],
            }
        ],
        "notes_ja": None,
        "sections": [
            {
                "id": "s1",
                "order": 1,
                "title": "Reading",
                "description_ja": None,
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
                            "explanation_ja": "本文の記述から判断できます。",
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
    }


@pytest.mark.parametrize(
    "missing_path",
    [
        "passage.kind",
        "passage.speaker_labels",
        "section.passage_ids",
        "explanation.wrong_choice_explanations_ja",
        "related_lemmas",
    ],
)
def test_generated_quiz_contract_requires_prompt_nested_fields(
    missing_path: str,
) -> None:
    payload = deepcopy(_complete_generated_quiz_payload())
    if missing_path == "passage.kind":
        del payload["passages"][0]["kind"]
    elif missing_path == "passage.speaker_labels":
        del payload["passages"][0]["speaker_labels"]
    elif missing_path == "section.passage_ids":
        del payload["sections"][0]["passage_ids"]
    elif missing_path == "explanation.wrong_choice_explanations_ja":
        del payload["sections"][0]["questions"][0]["explanation"][
            "wrong_choice_explanations_ja"
        ]
    elif missing_path == "related_lemmas":
        del payload["related_lemmas"]

    with pytest.raises(ValidationError):
        GeneratedQuizPayload.model_validate(payload)


def test_generated_quiz_contract_accepts_complete_prompt_shape() -> None:
    result = GeneratedQuizPayload.model_validate(_complete_generated_quiz_payload())

    assert result.passages[0].kind.value == "article"
