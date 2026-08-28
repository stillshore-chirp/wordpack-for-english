from __future__ import annotations

from ...models.quiz import QuizDifficulty, QuizDomainIntensity, QuizFormatProfile, QuizGenerationDomain


FORMAT_PROFILE_INSTRUCTIONS: dict[QuizFormatProfile, str] = {
    QuizFormatProfile.single_passage: (
        "Create one coherent English passage with clear paragraphs. Use one passage id, usually p1."
    ),
    QuizFormatProfile.multi_document: (
        "Create 2 to 4 short documents. Label each document clearly. Include questions that require comparing information across documents."
    ),
    QuizFormatProfile.dialogue_script: (
        "Create a natural dialogue, meeting, interview, or chat-style script with speaker labels."
    ),
    QuizFormatProfile.lecture_explanation: (
        "Create a monologue, mini lecture, explanation, or short analytical talk. Use definitions, examples, contrasts, or cause-effect relations."
    ),
    QuizFormatProfile.case_study: (
        "Create a scenario with context, constraints, a problem, data-like details, and a decision or evaluation point."
    ),
    QuizFormatProfile.mixed: (
        "Choose the structure that best fits the generation_domain and selected lemmas. You may combine more than one passage type."
    ),
}


GENERATION_DOMAIN_INSTRUCTIONS: dict[QuizGenerationDomain, str] = {
    QuizGenerationDomain.technical: (
        "Use technical contexts such as software development, AI, data systems, infrastructure, system design, debugging, observability, API design, product engineering, and engineering trade-offs. Avoid unsafe cyber instructions."
    ),
    QuizGenerationDomain.academic: (
        "Use academic contexts such as research design, theories, experiments, observations, evidence, concepts, education, language, psychology, social science, and natural science."
    ),
    QuizGenerationDomain.business: (
        "Use business contexts such as workplace operations, email, notices, meetings, procurement, sales, marketing, hiring, customer support, scheduling, and operational improvement."
    ),
    QuizGenerationDomain.daily: (
        "Use everyday contexts such as travel, housing, shopping, local activities, transportation, personal schedules, hobbies, friends, family, and everyday problems."
    ),
}


DOMAIN_INTENSITY_INSTRUCTIONS: dict[QuizDomainIntensity, str] = {
    QuizDomainIntensity.light: (
        "Keep domain-specific vocabulary light. Use accessible contexts and explain specialized ideas indirectly through the passage."
    ),
    QuizDomainIntensity.standard: (
        "Use a natural amount of domain-specific vocabulary and context for an intermediate learner."
    ),
    QuizDomainIntensity.deep: (
        "Use richer domain-specific vocabulary, concepts, constraints, and reasoning while keeping the answer unambiguous and the material educational."
    ),
}


DIFFICULTY_INSTRUCTIONS: dict[QuizDifficulty, str] = {
    QuizDifficulty.easy: (
        "Use clear paragraph structure, common vocabulary around the selected lemmas, and mostly direct evidence questions."
    ),
    QuizDifficulty.medium: (
        "Use natural intermediate reading density with a mix of detail, inference, main idea, and vocabulary questions."
    ),
    QuizDifficulty.hard: (
        "Use denser discourse, more inference, distractors that require careful evidence checking, and still unambiguous correct answers."
    ),
}


QUIZ_JSON_SCHEMA_PROMPT = """Return JSON only with this shape:
{
  "title_en": string,
  "format_profile": "single_passage" | "multi_document" | "dialogue_script" | "lecture_explanation" | "case_study" | "mixed",
  "generation_domain": "technical" | "academic" | "business" | "daily",
  "domain_intensity": "light" | "standard" | "deep",
  "difficulty": "easy" | "medium" | "hard",
  "passages": [
    {
      "id": string,
      "order": number,
      "kind": "article" | "document" | "email" | "notice" | "memo" | "table_text" | "dialogue" | "lecture" | "case",
      "title": string | null,
      "body_en": string,
      "body_ja": string | null,
      "speaker_labels": [string]
    }
  ],
  "notes_ja": string | null,
  "sections": [
    {
      "id": string,
      "order": number,
      "title": string,
      "description_ja": string | null,
      "passage_ids": [string],
      "questions": [
        {
          "id": string,
          "order": number,
          "type": "main_idea" | "detail" | "inference" | "vocabulary" | "reference" | "sentence_insertion" | "purpose" | "cross_reference" | "next_action" | "organization",
          "prompt": string,
          "choices": [{"id":"A","text":string},{"id":"B","text":string},{"id":"C","text":string},{"id":"D","text":string}],
          "correct_choice_id": "A" | "B" | "C" | "D",
          "explanation": {
            "explanation_ja": string,
            "evidence_passage_id": string | null,
            "evidence_text": string | null,
            "evidence_start": number | null,
            "evidence_end": number | null,
            "wrong_choice_explanations_ja": {"incorrect_choice_id": string},
            "related_lemmas": [string]
          }
        }
      ]
    }
  ],
  "related_lemmas": [string]
}"""


def build_quiz_generation_prompt(
    *,
    format_profile: QuizFormatProfile,
    generation_domain: QuizGenerationDomain,
    domain_intensity: QuizDomainIntensity,
    difficulty: QuizDifficulty,
    lemmas: list[str],
    section_count: int,
    questions_per_section: int,
    include_translation: bool,
    topic_seed: str | None,
    avoid_topics: list[str],
) -> str:
    source_lemmas = ", ".join(f'"{lemma}"' for lemma in lemmas) or "(none)"
    avoid = ", ".join(f'"{topic}"' for topic in avoid_topics) or "(none)"
    topic = topic_seed or "(none)"
    alignment_rule = (
        "Preserve the exact paragraph structure of body_en. "
        "In each corresponding paragraph, translate every English sentence into "
        "exactly one Japanese sentence in the same order. Do not split, combine, "
        "omit, or reorder sentences. End each Japanese sentence with 。, ？, or ！; "
        "when using a closing quotation mark, place it after that punctuation."
    )
    translation_rule = (
        f"Include Japanese body_ja translations for passages. {alignment_rule}"
        if include_translation
        else (
            "Set body_ja to null unless translation is essential for review. "
            f"If body_ja is included, {alignment_rule}"
        )
    )
    return f"""You are generating original English learning material for a private vocabulary app.
Do not reproduce copyrighted test questions, official sample passages, official directions, or brand-specific wording.
Do not mention any official test brand names.
Create an original quiz using only the requested generic structural format.

Generation controls:
- format_profile: {format_profile.value}
- format_profile instruction: {FORMAT_PROFILE_INSTRUCTIONS[format_profile]}
- generation_domain: {generation_domain.value}
- generation_domain instruction: {GENERATION_DOMAIN_INSTRUCTIONS[generation_domain]}
- domain_intensity: {domain_intensity.value}
- domain_intensity instruction: {DOMAIN_INTENSITY_INSTRUCTIONS[domain_intensity]}
- difficulty: {difficulty.value}
- difficulty instruction: {DIFFICULTY_INSTRUCTIONS[difficulty]}
- section_count: {section_count}
- questions_per_section: {questions_per_section}
- topic_seed: {topic}
- avoid_topics: {avoid}
- source lemmas: {source_lemmas}

Rules:
- format_profile controls passage and question structure.
- generation_domain controls topic, vocabulary, register, and situation.
- domain_intensity controls how strongly the selected domain appears.
- Include the provided lemmas naturally when possible.
- Do not force a lemma into an unnatural sentence.
- Avoid unsafe, illegal, or individually actionable medical/legal/financial advice.
- Create exactly {section_count} sections and exactly {questions_per_section} questions in each section.
- Each question must have exactly four choices A, B, C, D.
- evidence_text should be a complete supporting sentence or a concise contiguous excerpt. Do not return only a tiny keyword fragment when the surrounding clause is needed to understand the answer.
- explanation_ja must be in Japanese, detailed, and learner-friendly. Aim for about 2 to 4 clear Japanese sentences: explain what the question is asking, how the evidence supports the correct answer, and what trap or contrast learners should notice.
- wrong_choice_explanations_ja must include only incorrect choice ids and must omit correct_choice_id. For each incorrect choice, write a specific Japanese reason that references the passage or the logic gap; avoid terse labels such as "本文にありません" alone.
- {translation_rule}
- Return JSON only.

{QUIZ_JSON_SCHEMA_PROMPT}
"""
