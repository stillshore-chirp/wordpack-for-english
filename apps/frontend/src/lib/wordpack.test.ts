import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LLM_MODEL,
  DEFAULT_REASONING_EFFORT,
  SUPPORTED_LLM_MODELS,
  SUPPORTED_REASONING_EFFORTS,
  composeModelRequestFields,
  normalizeLlmModel,
} from './wordpack';

describe('Luna model configuration', () => {
  it('keeps a single Luna model option for future-select UI compatibility', () => {
    expect(SUPPORTED_LLM_MODELS).toEqual(['gpt-5.6-luna']);
    expect(DEFAULT_LLM_MODEL).toBe('gpt-5.6-luna');
  });

  it('normalizes legacy and unknown stored selections to Luna', () => {
    expect(normalizeLlmModel('gpt-5.4-mini')).toBe('gpt-5.6-luna');
    expect(normalizeLlmModel('gpt-5.4-nano')).toBe('gpt-5.6-luna');
    expect(normalizeLlmModel('unknown')).toBe('gpt-5.6-luna');
  });

  it('uses Luna High and medium verbosity by default', () => {
    expect(DEFAULT_REASONING_EFFORT).toBe('high');
    expect(SUPPORTED_REASONING_EFFORTS).toEqual([
      'none',
      'low',
      'medium',
      'high',
      'xhigh',
      'max',
    ]);
    expect(composeModelRequestFields({})).toEqual({
      model: 'gpt-5.6-luna',
      reasoning: { effort: 'high' },
      text: { verbosity: 'medium' },
    });
  });
});
