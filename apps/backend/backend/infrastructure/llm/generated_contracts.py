from __future__ import annotations

from pydantic import BaseModel, Field

from ...models.quiz import (
    QuizDifficulty,
    QuizDomainIntensity,
    QuizFormatProfile,
    QuizGenerationDomain,
    QuizPassage,
    QuizSection,
)
from ...models.word import Collocations, ContrastItem, Etymology, Sense


class GeneratedPronunciationPayload(BaseModel):
    ipa_RP: str


class GeneratedWordPackPayload(BaseModel):
    """build_wordpack_prompt がLLMへ要求する生成部分だけの契約。"""

    senses: list[Sense]
    sense_title: str
    collocations: Collocations
    contrast: list[ContrastItem]
    etymology: Etymology
    study_card: str
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


__all__ = ["GeneratedQuizPayload", "GeneratedWordPackPayload"]
