from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..domain.wordpack.lemma import validate_lemma
from ..llm_models import (
    ensure_supported_llm_model,
    ensure_supported_reasoning_options,
    ensure_supported_text_options,
)


QUIZ_PASSAGE_MAX_LENGTH = 12000
QUIZ_TITLE_MAX_LENGTH = 120


class QuizFormatProfile(str, Enum):
    single_passage = "single_passage"
    multi_document = "multi_document"
    dialogue_script = "dialogue_script"
    lecture_explanation = "lecture_explanation"
    case_study = "case_study"
    mixed = "mixed"


class QuizGenerationDomain(str, Enum):
    technical = "technical"
    academic = "academic"
    business = "business"
    daily = "daily"


class QuizDomainIntensity(str, Enum):
    light = "light"
    standard = "standard"
    deep = "deep"


class QuizDifficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class QuizPassageKind(str, Enum):
    article = "article"
    document = "document"
    email = "email"
    notice = "notice"
    memo = "memo"
    table_text = "table_text"
    dialogue = "dialogue"
    lecture = "lecture"
    case = "case"


class QuizQuestionType(str, Enum):
    main_idea = "main_idea"
    detail = "detail"
    inference = "inference"
    vocabulary = "vocabulary"
    reference = "reference"
    sentence_insertion = "sentence_insertion"
    purpose = "purpose"
    cross_reference = "cross_reference"
    next_action = "next_action"
    organization = "organization"


class QuizPassage(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    order: int = Field(ge=1)
    kind: QuizPassageKind = QuizPassageKind.article
    title: str | None = Field(default=None, max_length=120)
    body_en: str = Field(min_length=1, max_length=QUIZ_PASSAGE_MAX_LENGTH)
    body_ja: str | None = Field(default=None, max_length=QUIZ_PASSAGE_MAX_LENGTH)
    speaker_labels: list[str] = Field(default_factory=list, max_length=10)


class QuizChoice(BaseModel):
    id: Literal["A", "B", "C", "D"]
    text: str = Field(min_length=1, max_length=500)


class QuizExplanation(BaseModel):
    explanation_ja: str = Field(min_length=1, max_length=2500)
    evidence_passage_id: str | None = Field(default=None, max_length=64)
    evidence_text: str | None = Field(default=None, max_length=1000)
    evidence_start: int | None = Field(default=None, ge=0)
    evidence_end: int | None = Field(default=None, ge=0)
    wrong_choice_explanations_ja: dict[str, str] = Field(default_factory=dict)
    related_lemmas: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def ensure_evidence_range_order(self) -> "QuizExplanation":
        if (
            self.evidence_start is not None
            and self.evidence_end is not None
            and self.evidence_end < self.evidence_start
        ):
            raise ValueError("evidence_end must be greater than or equal to evidence_start")
        return self


class QuizQuestion(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    order: int = Field(ge=1)
    type: QuizQuestionType
    prompt: str = Field(min_length=1, max_length=1000)
    choices: list[QuizChoice] = Field(min_length=4, max_length=4)
    correct_choice_id: Literal["A", "B", "C", "D"]
    explanation: QuizExplanation

    @model_validator(mode="after")
    def ensure_correct_choice_exists(self) -> "QuizQuestion":
        choice_ids = {choice.id for choice in self.choices}
        if len(choice_ids) != 4:
            raise ValueError("choices must include A, B, C and D exactly once")
        if self.correct_choice_id not in choice_ids:
            raise ValueError("correct_choice_id must be included in choices")
        return self


class QuizSection(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    order: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=120)
    description_ja: str | None = Field(default=None, max_length=500)
    passage_ids: list[str] = Field(default_factory=list, max_length=10)
    questions: list[QuizQuestion] = Field(min_length=1, max_length=10)


class QuizWordPackOccurrence(BaseModel):
    passage_id: str | None = Field(default=None, max_length=64)
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def ensure_range_order(self) -> "QuizWordPackOccurrence":
        if self.end < self.start:
            raise ValueError("end must be greater than or equal to start")
        return self


class QuizWordPackLink(BaseModel):
    word_pack_id: str | None = None
    lemma: str = Field(min_length=1, max_length=64)
    status: Literal["existing", "created", "missing", "generated_requested", "skipped"]
    is_empty: bool = False
    occurrences: list[QuizWordPackOccurrence] = Field(default_factory=list)
    warning: str | None = None


class Quiz(BaseModel):
    id: str
    title_en: str = Field(min_length=1, max_length=QUIZ_TITLE_MAX_LENGTH)
    format_profile: QuizFormatProfile
    generation_domain: QuizGenerationDomain
    domain_intensity: QuizDomainIntensity = QuizDomainIntensity.standard
    difficulty: QuizDifficulty = QuizDifficulty.medium
    passages: list[QuizPassage] = Field(min_length=1, max_length=8)
    notes_ja: str | None = Field(default=None, max_length=3000)
    sections: list[QuizSection] = Field(min_length=1, max_length=8)
    related_word_packs: list[QuizWordPackLink] = Field(default_factory=list)
    source_word_pack_ids: list[str] = Field(default_factory=list)
    source_lemmas: list[str] = Field(default_factory=list)
    topic_seed: str | None = Field(default=None, max_length=200)
    avoid_topics: list[str] = Field(default_factory=list, max_length=20)
    llm_model: str | None = None
    llm_params: str | None = None
    generation_started_at: str | None = None
    generation_completed_at: str | None = None
    generation_duration_ms: int | None = Field(default=None, ge=0)
    guest_public: bool = False
    created_at: str
    updated_at: str

    @model_validator(mode="after")
    def ensure_internal_references(self) -> "Quiz":
        passage_ids = {passage.id for passage in self.passages}
        if len(passage_ids) != len(self.passages):
            raise ValueError("passage ids must be unique")
        section_ids = {section.id for section in self.sections}
        if len(section_ids) != len(self.sections):
            raise ValueError("section ids must be unique")
        question_ids: set[str] = set()
        for section in self.sections:
            for passage_id in section.passage_ids:
                if passage_id not in passage_ids:
                    raise ValueError("section.passage_ids must reference existing passages")
            for question in section.questions:
                if question.id in question_ids:
                    raise ValueError("question ids must be unique")
                question_ids.add(question.id)
                evidence_passage_id = question.explanation.evidence_passage_id
                if evidence_passage_id and evidence_passage_id not in passage_ids:
                    raise ValueError("question evidence_passage_id must reference an existing passage")
        return self


class QuizGenerateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    format_profile: QuizFormatProfile = QuizFormatProfile.single_passage
    generation_domain: QuizGenerationDomain = QuizGenerationDomain.technical
    domain_intensity: QuizDomainIntensity = QuizDomainIntensity.standard
    difficulty: QuizDifficulty = QuizDifficulty.medium
    word_pack_ids: list[str] = Field(default_factory=list, max_length=20)
    lemmas: list[str] = Field(default_factory=list, max_length=30)
    section_count: int = Field(default=2, ge=1, le=4)
    questions_per_section: int = Field(default=3, ge=1, le=5)
    include_translation: bool = True
    topic_seed: str | None = Field(default=None, max_length=200)
    avoid_topics: list[str] = Field(default_factory=list, max_length=20)
    model: str | None = None
    reasoning: dict | None = None
    text: dict | None = None

    @field_validator("model")
    @classmethod
    def ensure_model_supported(cls, value: str | None) -> str | None:
        return ensure_supported_llm_model(value) if value else value

    @field_validator("reasoning")
    @classmethod
    def ensure_reasoning_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_reasoning_options(value)

    @field_validator("text")
    @classmethod
    def ensure_text_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_text_options(value)

    @field_validator("lemmas")
    @classmethod
    def ensure_lemmas_safe(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            candidate = str(value or "").strip()
            if not candidate:
                continue
            lemma = validate_lemma(candidate)
            key = lemma.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(lemma)
        return normalized

    @field_validator("avoid_topics")
    @classmethod
    def normalize_avoid_topics(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            item = str(value or "").strip()
            if not item:
                continue
            key = item.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(item)
        return normalized

    @model_validator(mode="after")
    def ensure_sources_exist(self) -> "QuizGenerateRequest":
        if not self.word_pack_ids and not self.lemmas:
            raise ValueError("word_pack_ids or lemmas is required")
        return self


class QuizListItem(BaseModel):
    id: str
    title_en: str
    format_profile: QuizFormatProfile
    generation_domain: QuizGenerationDomain
    domain_intensity: QuizDomainIntensity
    difficulty: QuizDifficulty
    question_count: int
    passage_count: int
    source_lemmas: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    guest_public: bool = False


class QuizListResponse(BaseModel):
    items: list[QuizListItem]
    total: int
    limit: int
    offset: int


class QuizGuestPublicUpdateRequest(BaseModel):
    guest_public: bool = Field(description="Quizをゲスト閲覧へ公開するか")


class QuizGuestPublicUpdateResponse(BaseModel):
    quiz_id: str
    guest_public: bool = Field(description="更新後のゲスト公開フラグ")


class QuizAnswerInput(BaseModel):
    question_id: str
    selected_choice_id: Literal["A", "B", "C", "D"] | None = None


class QuizAttemptRequest(BaseModel):
    answers: list[QuizAnswerInput] = Field(default_factory=list)
    started_at: str | None = None
    elapsed_ms: int | None = Field(default=None, ge=0)


class QuizQuestionResult(BaseModel):
    question_id: str
    selected_choice_id: str | None
    correct_choice_id: str
    is_correct: bool


class QuizAttemptResponse(BaseModel):
    id: str
    quiz_id: str
    score: int
    total: int
    percentage: float
    results: list[QuizQuestionResult]
    started_at: str | None = None
    submitted_at: str
    elapsed_ms: int | None = None


class QuizGenerationJobResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    quiz_id: str | None = None
    result: Quiz | None = None
    error: str | None = None
