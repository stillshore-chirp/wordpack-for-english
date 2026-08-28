import { describe, expect, it } from 'vitest';

import { formatQuizGenerationProgress } from './progress';

describe('formatQuizGenerationProgress', () => {
  it.each([
    ['generation', 1, 'Quizを生成しています（1/5）'],
    ['json_repair', 2, '生成結果を確認・修復しています（2/5）'],
    ['translation_alignment', 3, '文対応を再確認しています（3/5）'],
  ])('formats %s phase', (retryPhase, attemptCount, expected) => {
    expect(formatQuizGenerationProgress({
      attempt_count: attemptCount,
      attempt_limit: 5,
      retry_phase: retryPhase,
    })).toBe(expected);
  });

  it('falls back for corrupt or unknown progress', () => {
    expect(formatQuizGenerationProgress({
      attempt_count: 6,
      attempt_limit: 5,
      retry_phase: 'translation_alignment',
    })).toBe('長文と設問を生成しています。');
  });
});
