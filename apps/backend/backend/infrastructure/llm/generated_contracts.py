from __future__ import annotations

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
    "has_required_wordpack_text",
]
