export interface QuizGenerationProgressState {
  attempt_count?: number | null;
  attempt_limit?: number | null;
  retry_phase?: string | null;
}

export const formatQuizGenerationProgress = (
  progress: QuizGenerationProgressState,
): string => {
  const attempt = progress.attempt_count;
  const limit = progress.attempt_limit;
  if (
    !Number.isInteger(attempt)
    || !Number.isInteger(limit)
    || (attempt ?? 0) < 1
    || (limit ?? 0) < 1
    || (attempt ?? 0) > (limit ?? 0)
  ) {
    return '長文と設問を生成しています。';
  }
  const count = `（${attempt}/${limit}）`;
  if (progress.retry_phase === 'json_repair') {
    return `生成結果を確認・修復しています${count}`;
  }
  if (progress.retry_phase === 'translation_alignment') {
    return `文対応を再確認しています${count}`;
  }
  if (progress.retry_phase === 'generation') {
    return `Quizを生成しています${count}`;
  }
  return '長文と設問を生成しています。';
};
