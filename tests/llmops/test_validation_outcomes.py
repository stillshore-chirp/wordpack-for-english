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
