from __future__ import annotations

import pytest

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
