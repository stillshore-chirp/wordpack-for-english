export interface Pronunciation {
  ipa_GA?: string | null;
  ipa_RP?: string | null;
  syllables?: number | null;
  stress_index?: number | null;
  linking_notes: string[];
}

export interface Sense {
  id: string;
  gloss_ja: string;
  definition_ja?: string | null;
  nuances_ja?: string | null;
  term_overview_ja?: string | null;
  term_core_ja?: string | null;
  patterns: string[];
  synonyms?: string[];
  antonyms?: string[];
  register?: string | null;
  notes_ja?: string | null;
}

export interface CollocationLists { verb_object: string[]; adj_noun: string[]; prep_noun: string[] }
export interface Collocations { general: CollocationLists; academic: CollocationLists }

export interface ContrastItem { with: string; diff_ja: string }

export interface ExampleItem { en: string; ja: string; grammar_ja?: string; llm_model?: string; llm_params?: string }
export interface Examples { Dev: ExampleItem[]; CS: ExampleItem[]; LLM: ExampleItem[]; Business: ExampleItem[]; Common: ExampleItem[] }
export type ExampleCategory = keyof Examples;
export type ExampleCounts = Record<ExampleCategory, number>;

export interface Etymology { note: string; confidence: 'low' | 'medium' | 'high' }

export interface Citation { text: string; meta?: Record<string, any> }

export interface WordPack {
  id?: string | null;
  lemma: string;
  sense_title: string;
  pronunciation: Pronunciation;
  senses: Sense[];
  collocations: Collocations;
  contrast: ContrastItem[];
  examples: Examples;
  etymology: Etymology;
  study_card: string;
  citations: Citation[];
  confidence: 'low' | 'medium' | 'high';
  guest_public?: boolean;
  checked_only_count?: number;
  learned_count?: number;
}

export interface WordPackListItem {
  id: string;
  lemma: string;
  sense_title?: string;
  created_at: string;
  updated_at: string;
  is_empty?: boolean;
  guest_public?: boolean;
  examples_count?: ExampleCounts | null;
  checked_only_count: number;
  learned_count: number;
}

export interface WordPackListFacetCounts {
  public: number;
  private: number;
  generated: number;
  not_generated: number;
}

export interface WordPackListResponse {
  items: WordPackListItem[];
  total: number;
  filtered_total?: number;
  facet_counts?: WordPackListFacetCounts;
  limit: number;
  offset: number;
}
