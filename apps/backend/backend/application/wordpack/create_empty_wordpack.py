from __future__ import annotations

from ...models.word import DEFAULT_ETYMOLOGY_PLACEHOLDER, WordPack
from ...sense_title import choose_sense_title


def build_empty_wordpack(lemma: str, *, generated_title: str | None = None) -> WordPack:
    return WordPack(
        lemma=lemma,
        sense_title=(
            generated_title or choose_sense_title(None, [], lemma=lemma, limit=20)
        ),
        pronunciation={
            "ipa_GA": None,
            "ipa_RP": None,
            "syllables": None,
            "stress_index": None,
            "linking_notes": [],
        },
        senses=[],
        collocations={
            "general": {"verb_object": [], "adj_noun": [], "prep_noun": []},
            "academic": {"verb_object": [], "adj_noun": [], "prep_noun": []},
        },
        contrast=[],
        examples={"Dev": [], "CS": [], "LLM": [], "Business": [], "Common": []},
        etymology={"note": DEFAULT_ETYMOLOGY_PLACEHOLDER, "confidence": "low"},
        study_card="",
        citations=[],
        confidence="low",
    )
