from __future__ import annotations

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))

from backend.domain.quiz.prompt_policy import build_quiz_generation_prompt
from backend.models.quiz import (
    QuizDifficulty,
    QuizDomainIntensity,
    QuizFormatProfile,
    QuizGenerationDomain,
)


def test_quiz_prompt_requests_aligned_translation_paragraphs_and_detailed_explanations() -> None:
    prompt = build_quiz_generation_prompt(
        format_profile=QuizFormatProfile.single_passage,
        generation_domain=QuizGenerationDomain.technical,
        domain_intensity=QuizDomainIntensity.standard,
        difficulty=QuizDifficulty.medium,
        lemmas=["latency"],
        section_count=1,
        questions_per_section=1,
        include_translation=True,
        topic_seed=None,
        avoid_topics=[],
    )

    assert "Preserve the exact paragraph structure of body_en" in prompt
    assert "translate every English sentence into exactly one Japanese sentence" in prompt
    assert "Do not split, combine, omit, or reorder sentences" in prompt
    assert "about 2 to 4 clear Japanese sentences" in prompt
    assert "must include only incorrect choice ids" in prompt
    assert "must omit correct_choice_id" in prompt
    assert "Do not return only a tiny keyword fragment" in prompt
