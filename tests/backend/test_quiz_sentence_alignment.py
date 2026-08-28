from __future__ import annotations

import json
from pathlib import Path

from backend.domain.quiz.sentence_alignment import (
    split_english_sentences,
    split_japanese_sentences,
    split_paragraphs,
    translation_alignment_issue,
)


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "quiz_sentence_alignment.json"


def _fixtures() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_sentence_alignment_matches_shared_fixture() -> None:
    for fixture in _fixtures():
        body_en = str(fixture["body_en"])
        body_ja = str(fixture["body_ja"])
        assert [
            len(split_english_sentences(paragraph))
            for paragraph in split_paragraphs(body_en)
        ] == fixture["english_sentence_counts"], fixture["name"]
        assert [
            len(split_japanese_sentences(paragraph))
            for paragraph in split_paragraphs(body_ja)
        ] == fixture["japanese_sentence_counts"], fixture["name"]
        assert (translation_alignment_issue(body_en, body_ja) is None) is fixture["valid"], fixture["name"]


def test_sentence_alignment_reports_the_mismatched_paragraph_without_text() -> None:
    fixture = next(
        item for item in _fixtures() if item["name"] == "same_total_but_different_per_paragraph"
    )

    issue = translation_alignment_issue(str(fixture["body_en"]), str(fixture["body_ja"]))

    assert issue is not None
    assert issue.reason == "sentence_count_mismatch"
    assert issue.paragraph_index == 1
    assert issue.english_sentence_count == 1
    assert issue.japanese_sentence_count == 2
