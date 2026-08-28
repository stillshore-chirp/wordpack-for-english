export type QuizFormatProfile =
  | 'single_passage'
  | 'multi_document'
  | 'dialogue_script'
  | 'lecture_explanation'
  | 'case_study'
  | 'mixed';

export type QuizGenerationDomain = 'technical' | 'academic' | 'business' | 'daily';
export type QuizDomainIntensity = 'light' | 'standard' | 'deep';
export type QuizDifficulty = 'easy' | 'medium' | 'hard';
export type QuizChoiceId = 'A' | 'B' | 'C' | 'D';

export type QuizPassageKind =
  | 'article'
  | 'document'
  | 'email'
  | 'notice'
  | 'memo'
  | 'table_text'
  | 'dialogue'
  | 'lecture'
  | 'case';

export type QuizQuestionType =
  | 'main_idea'
  | 'detail'
  | 'inference'
  | 'vocabulary'
  | 'reference'
  | 'sentence_insertion'
  | 'purpose'
  | 'cross_reference'
  | 'next_action'
  | 'organization';

export interface QuizPassage {
  id: string;
  order: number;
  kind: QuizPassageKind;
  title?: string | null;
  body_en: string;
  body_ja?: string | null;
  speaker_labels: string[];
}

export interface QuizChoice {
  id: QuizChoiceId;
  text: string;
}

export interface QuizExplanation {
  explanation_ja: string;
  evidence_passage_id?: string | null;
  evidence_text?: string | null;
  evidence_start?: number | null;
  evidence_end?: number | null;
  wrong_choice_explanations_ja: Record<string, string>;
  related_lemmas: string[];
}

export interface QuizQuestion {
  id: string;
  order: number;
  type: QuizQuestionType;
  prompt: string;
  choices: QuizChoice[];
  correct_choice_id: QuizChoiceId;
  explanation: QuizExplanation;
}

export interface QuizSection {
  id: string;
  order: number;
  title: string;
  description_ja?: string | null;
  passage_ids: string[];
  questions: QuizQuestion[];
}

export interface QuizWordPackOccurrence {
  passage_id?: string | null;
  start: number;
  end: number;
}

export interface QuizWordPackLink {
  word_pack_id?: string | null;
  lemma: string;
  status: 'existing' | 'created' | 'missing' | 'generated_requested' | 'skipped';
  is_empty?: boolean;
  occurrences?: QuizWordPackOccurrence[];
  warning?: string | null;
}

export interface Quiz {
  id: string;
  title_en: string;
  format_profile: QuizFormatProfile;
  generation_domain: QuizGenerationDomain;
  domain_intensity: QuizDomainIntensity;
  difficulty: QuizDifficulty;
  passages: QuizPassage[];
  notes_ja?: string | null;
  sections: QuizSection[];
  related_word_packs: QuizWordPackLink[];
  source_word_pack_ids: string[];
  source_lemmas: string[];
  topic_seed?: string | null;
  avoid_topics?: string[];
  llm_model?: string | null;
  llm_params?: string | null;
  translation_alignment_version?: 'deterministic_v1' | null;
  created_at: string;
  updated_at: string;
  guest_public?: boolean;
}

export interface QuizListItem {
  id: string;
  title_en: string;
  format_profile: QuizFormatProfile;
  generation_domain: QuizGenerationDomain;
  domain_intensity: QuizDomainIntensity;
  difficulty: QuizDifficulty;
  question_count: number;
  passage_count: number;
  source_lemmas: string[];
  created_at: string;
  updated_at: string;
  guest_public?: boolean;
}

export interface QuizListResponse {
  items: QuizListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface QuizGenerateRequest {
  format_profile: QuizFormatProfile;
  generation_domain: QuizGenerationDomain;
  domain_intensity: QuizDomainIntensity;
  difficulty: QuizDifficulty;
  word_pack_ids: string[];
  lemmas: string[];
  section_count: number;
  questions_per_section: number;
  include_translation: boolean;
  topic_seed?: string | null;
  avoid_topics?: string[];
  model?: string | null;
  reasoning?: Record<string, unknown> | null;
  text?: Record<string, unknown> | null;
}

export interface QuizGenerationJobResponse {
  job_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  quiz_id?: string | null;
  result?: Quiz | null;
  error?: string | null;
  error_code?: string | null;
  attempt_count?: number;
  attempt_limit?: number;
  retry_phase?: 'generation' | 'json_repair' | 'translation_alignment' | null;
}

export interface QuizAnswerInput {
  question_id: string;
  selected_choice_id?: QuizChoiceId | null;
}

export interface QuizAttemptRequest {
  answers: QuizAnswerInput[];
  started_at?: string | null;
  elapsed_ms?: number | null;
}

export interface QuizQuestionResult {
  question_id: string;
  selected_choice_id?: string | null;
  correct_choice_id: string;
  is_correct: boolean;
}

export interface QuizAttemptResponse {
  id: string;
  quiz_id: string;
  score: number;
  total: number;
  percentage: number;
  results: QuizQuestionResult[];
  started_at?: string | null;
  submitted_at: string;
  elapsed_ms?: number | null;
}
