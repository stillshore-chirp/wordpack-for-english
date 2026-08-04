from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from ...models.quiz import (
    QuizDifficulty,
    QuizDomainIntensity,
    QuizFormatProfile,
    QuizGenerationDomain,
    QuizExplanation,
    QuizPassage,
    QuizPassageKind,
    QuizQuestion,
    QuizSection,
)
from ...models.common import ConfidenceLevel
from ...models.word import ContrastItem


class GeneratedSensePayload(BaseModel):
    """build_wordpack_prompt が各語義へ要求する必須キー。"""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(min_length=1)
    gloss_ja: str = Field(min_length=1)
    definition_ja: str = Field(min_length=1)
    nuances_ja: str = Field(min_length=1)
    patterns: list[str]
    synonyms: list[str]
    antonyms: list[str]
    register_: str = Field(alias="register", min_length=1)
    notes_ja: str = Field(min_length=1)
    term_overview_ja: str | None = None
    term_core_ja: str | None = None


class GeneratedCollocationListsPayload(BaseModel):
    verb_object: list[str]
    adj_noun: list[str]
    prep_noun: list[str]


class GeneratedCollocationsPayload(BaseModel):
    general: GeneratedCollocationListsPayload
    academic: GeneratedCollocationListsPayload


class GeneratedEtymologyPayload(BaseModel):
    note: str = Field(min_length=1)
    confidence: ConfidenceLevel


class GeneratedPronunciationPayload(BaseModel):
    ipa_RP: str = Field(min_length=1)


class GeneratedWordPackPayload(BaseModel):
    """build_wordpack_prompt がLLMへ要求する生成部分だけの契約。"""

    senses: list[GeneratedSensePayload] = Field(min_length=1)
    sense_title: str = Field(min_length=1)
    collocations: GeneratedCollocationsPayload
    contrast: list[ContrastItem]
    etymology: GeneratedEtymologyPayload
    study_card: str = Field(min_length=1)
    pronunciation: GeneratedPronunciationPayload


@dataclass(frozen=True)
class GeneratedWordPackNormalization:
    """意味を補完せずに正規化した生成結果と安全な観測情報。"""

    payload: GeneratedWordPackPayload
    changed_items: int
    removed_items: int
    field_categories: tuple[str, ...]


def normalize_generated_wordpack_payload(
    payload: GeneratedWordPackPayload,
) -> GeneratedWordPackNormalization:
    """空白を整え、意味を持たないコレクション要素だけを除去する。"""

    changed_items = 0
    removed_items = 0
    field_categories: set[str] = set()

    def clean_required(value: str, category: str) -> str:
        nonlocal changed_items
        cleaned = value.strip()
        if cleaned != value:
            changed_items += 1
            field_categories.add(category)
        return cleaned

    def clean_optional(value: str | None, category: str) -> str | None:
        nonlocal changed_items
        if value is None:
            return None
        cleaned = value.strip()
        normalized = cleaned or None
        if normalized != value:
            changed_items += 1
            field_categories.add(category)
        return normalized

    def clean_list(values: list[str], category: str) -> list[str]:
        nonlocal changed_items, removed_items
        normalized: list[str] = []
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                changed_items += 1
                removed_items += 1
                field_categories.add(category)
                continue
            if cleaned != value:
                changed_items += 1
                field_categories.add(category)
            normalized.append(cleaned)
        return normalized

    senses: list[GeneratedSensePayload] = []
    for sense in payload.senses:
        senses.append(
            sense.model_copy(
                update={
                    "id": clean_required(sense.id, "sense.required_text"),
                    "gloss_ja": clean_required(
                        sense.gloss_ja, "sense.required_text"
                    ),
                    "definition_ja": clean_required(
                        sense.definition_ja, "sense.required_text"
                    ),
                    "nuances_ja": clean_required(
                        sense.nuances_ja, "sense.required_text"
                    ),
                    "patterns": clean_list(sense.patterns, "sense.patterns"),
                    "synonyms": clean_list(sense.synonyms, "sense.synonyms"),
                    "antonyms": clean_list(sense.antonyms, "sense.antonyms"),
                    "register_": clean_required(
                        sense.register_, "sense.required_text"
                    ),
                    "notes_ja": clean_required(
                        sense.notes_ja, "sense.required_text"
                    ),
                    "term_overview_ja": clean_optional(
                        sense.term_overview_ja, "sense.optional_text"
                    ),
                    "term_core_ja": clean_optional(
                        sense.term_core_ja, "sense.optional_text"
                    ),
                }
            )
        )

    def clean_collocation_group(
        group: GeneratedCollocationListsPayload, category: str
    ) -> GeneratedCollocationListsPayload:
        return group.model_copy(
            update={
                "verb_object": clean_list(group.verb_object, category),
                "adj_noun": clean_list(group.adj_noun, category),
                "prep_noun": clean_list(group.prep_noun, category),
            }
        )

    contrast: list[ContrastItem] = []
    for item in payload.contrast:
        with_text = item.with_.strip()
        diff_text = item.diff_ja.strip()
        if not with_text or not diff_text:
            changed_items += 1
            removed_items += 1
            field_categories.add("contrast")
            continue
        if with_text != item.with_ or diff_text != item.diff_ja:
            changed_items += 1
            field_categories.add("contrast")
        contrast.append(
            item.model_copy(update={"with_": with_text, "diff_ja": diff_text})
        )

    normalized = payload.model_copy(
        update={
            "senses": senses,
            "sense_title": clean_required(
                payload.sense_title, "wordpack.required_text"
            ),
            "collocations": payload.collocations.model_copy(
                update={
                    "general": clean_collocation_group(
                        payload.collocations.general, "collocations.general"
                    ),
                    "academic": clean_collocation_group(
                        payload.collocations.academic, "collocations.academic"
                    ),
                }
            ),
            "contrast": contrast,
            "etymology": payload.etymology.model_copy(
                update={
                    "note": clean_required(payload.etymology.note, "etymology.note")
                }
            ),
            "study_card": clean_required(
                payload.study_card, "wordpack.required_text"
            ),
            "pronunciation": payload.pronunciation.model_copy(
                update={
                    "ipa_RP": clean_required(
                        payload.pronunciation.ipa_RP, "pronunciation.ipa_RP"
                    )
                }
            ),
        }
    )
    return GeneratedWordPackNormalization(
        payload=normalized,
        changed_items=changed_items,
        removed_items=removed_items,
        field_categories=tuple(sorted(field_categories)),
    )


def required_wordpack_text_issues(
    payload: GeneratedWordPackPayload,
) -> tuple[str, ...]:
    """安全に補完できない空白文字列のフィールド種別を返す。"""

    issues: set[str] = set()
    if not payload.sense_title.strip() or not payload.study_card.strip():
        issues.add("wordpack.required_text")
    if not payload.etymology.note.strip():
        issues.add("etymology.note")
    if not payload.pronunciation.ipa_RP.strip():
        issues.add("pronunciation.ipa_RP")
    if any(
        not value.strip()
        for sense in payload.senses
        for value in (
            sense.id,
            sense.gloss_ja,
            sense.definition_ja,
            sense.nuances_ja,
            sense.register_,
            sense.notes_ja,
        )
    ):
        issues.add("sense.required_text")
    return tuple(sorted(issues))


def has_required_wordpack_text(payload: GeneratedWordPackPayload) -> bool:
    """生成契約で要求する文字列が空白だけでないことを確認する。"""

    required_text = [
        payload.sense_title,
        payload.study_card,
        payload.etymology.note,
        payload.pronunciation.ipa_RP,
        *(
            value
            for sense in payload.senses
            for value in (
                sense.id,
                sense.gloss_ja,
                sense.definition_ja,
                sense.nuances_ja,
                sense.register_,
                sense.notes_ja,
            )
        ),
        *(
            value
            for sense in payload.senses
            for values in (sense.patterns, sense.synonyms, sense.antonyms)
            for value in values
        ),
        *(
            value
            for group in (
                payload.collocations.general,
                payload.collocations.academic,
            )
            for values in (group.verb_object, group.adj_noun, group.prep_noun)
            for value in values
        ),
        *(
            value
            for contrast in payload.contrast
            for value in (contrast.with_, contrast.diff_ja)
        ),
    ]
    optional_text = [
        value
        for sense in payload.senses
        for value in (sense.term_overview_ja, sense.term_core_ja)
        if value is not None
    ]
    return all(value.strip() for value in (*required_text, *optional_text))


class GeneratedQuizPassagePayload(QuizPassage):
    """QUIZ_JSON_SCHEMA_PROMPT がpassageへ要求する全キー。"""

    kind: QuizPassageKind
    title: str | None = Field(max_length=120)
    body_ja: str | None = Field(max_length=12000)
    speaker_labels: list[str] = Field(max_length=10)


class GeneratedQuizExplanationPayload(QuizExplanation):
    """QUIZ_JSON_SCHEMA_PROMPT がexplanationへ要求する全キー。"""

    evidence_passage_id: str | None = Field(max_length=64)
    evidence_text: str | None = Field(max_length=1000)
    evidence_start: int | None = Field(ge=0)
    evidence_end: int | None = Field(ge=0)
    wrong_choice_explanations_ja: dict[str, str]
    related_lemmas: list[str] = Field(max_length=20)


class GeneratedQuizQuestionPayload(QuizQuestion):
    explanation: GeneratedQuizExplanationPayload


class GeneratedQuizSectionPayload(QuizSection):
    description_ja: str | None = Field(max_length=500)
    passage_ids: list[str] = Field(max_length=10)
    questions: list[GeneratedQuizQuestionPayload] = Field(min_length=1, max_length=10)


class GeneratedQuizPayload(BaseModel):
    """QUIZ_JSON_SCHEMA_PROMPT がLLMへ要求する生成部分だけの契約。"""

    title_en: str = Field(min_length=1, max_length=120)
    format_profile: QuizFormatProfile
    generation_domain: QuizGenerationDomain
    domain_intensity: QuizDomainIntensity
    difficulty: QuizDifficulty
    passages: list[GeneratedQuizPassagePayload] = Field(min_length=1, max_length=8)
    notes_ja: str | None = Field(max_length=3000)
    sections: list[GeneratedQuizSectionPayload] = Field(min_length=1, max_length=8)
    related_lemmas: list[str] = Field(max_length=20)


__all__ = [
    "GeneratedQuizPayload",
    "GeneratedWordPackPayload",
    "GeneratedWordPackNormalization",
    "normalize_generated_wordpack_payload",
    "required_wordpack_text_issues",
    "has_required_wordpack_text",
]
