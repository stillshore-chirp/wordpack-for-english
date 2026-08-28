from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal


QUIZ_GENERATION_ATTEMPT_LIMIT = 5
QuizGenerationPhase = Literal["generation", "json_repair", "translation_alignment"]


@dataclass(frozen=True)
class QuizGenerationProgress:
    attempt_count: int
    attempt_limit: int
    retry_phase: QuizGenerationPhase


QuizGenerationProgressCallback = Callable[[QuizGenerationProgress], None]


__all__ = [
    "QUIZ_GENERATION_ATTEMPT_LIMIT",
    "QuizGenerationPhase",
    "QuizGenerationProgress",
    "QuizGenerationProgressCallback",
]
