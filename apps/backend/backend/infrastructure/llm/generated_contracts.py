from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...models.quiz import (
    QuizDifficulty,
    QuizDomainIntensity,
    QuizFormatProfile,
    QuizGenerationDomain,
    QuizPassage,
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


class GeneratedQuizPayload(BaseModel):
    """QUIZ_JSON_SCHEMA_PROMPT がLLMへ要求する生成部分だけの契約。"""

    title_en: str = Field(min_length=1, max_length=120)
    format_profile: QuizFormatProfile
    generation_domain: QuizGenerationDomain
    domain_intensity: QuizDomainIntensity
    difficulty: QuizDifficulty
    passages: list[QuizPassage] = Field(min_length=1, max_length=8)
    notes_ja: str | None = Field(default=None, max_length=3000)
    sections: list[QuizSection] = Field(min_length=1, max_length=8)
    related_lemmas: list[str] = Field(default_factory=list)


__all__ = [
    "GeneratedQuizPayload",
    "GeneratedWordPackPayload",
]
