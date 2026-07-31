import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createArticleImportJob,
  fetchArticleImportJob,
} from '../../features/article-import/api/articleApi';
import type { WordPack } from '../useWordPack';
import { useExampleActions } from '../useExampleActions';

vi.mock('../../features/article-import/api/articleApi', () => ({
  createArticleImportJob: vi.fn(),
  fetchArticleImportJob: vi.fn(),
}));

const makeWordPack = (): WordPack => ({
  lemma: 'alpha',
  sense_title: 'alpha',
  pronunciation: { linking_notes: [] },
  senses: [],
  collocations: {
    general: { verb_object: [], adj_noun: [], prep_noun: [] },
    academic: { verb_object: [], adj_noun: [], prep_noun: [] },
  },
  contrast: [],
  examples: {
    Dev: [{ en: 'Example sentence.', ja: '例文です。' }],
    CS: [],
    LLM: [],
    Business: [],
    Common: [],
  },
  etymology: { note: '', confidence: 'low' },
  study_card: '',
  citations: [],
  confidence: 'low',
});

describe('useExampleActions.importArticleFromExample', () => {
  const notify = {
    add: vi.fn(() => 'notification:test'),
    update: vi.fn(),
  };
  const setStatusMessage = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    notify.add.mockClear();
    notify.update.mockClear();
    setStatusMessage.mockClear();
    vi.mocked(createArticleImportJob).mockResolvedValue({
      job_id: 'article-import-job:example',
      status: 'running',
    });
    vi.mocked(fetchArticleImportJob).mockRejectedValue(
      new Error('status temporarily unavailable'),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('ジョブ受付後の一時的な状態取得失敗を進行中のまま再照合可能にする', async () => {
    const { result } = renderHook(() => useExampleActions({
      apiBase: '/api',
      requestTimeoutMs: 60_000,
      generationRequestTimeoutMs: 1_500_000,
      currentWordPackId: 'wp:alpha',
      data: makeWordPack(),
      model: 'gpt-5.6-luna',
      reasoningEffort: 'high',
      textVerbosity: 'medium',
      setStatusMessage,
      loadWordPack: vi.fn(),
      notify,
      confirmDialog: vi.fn(),
    }));

    await act(async () => {
      const importPromise = result.current.importArticleFromExample('Dev', 0);
      await vi.advanceTimersByTimeAsync(1000);
      await importPromise;
    });

    expect(setStatusMessage).toHaveBeenLastCalledWith({
      kind: 'alert',
      text: '文章インポートはバックグラウンドで継続しています。生成キューから状態を確認してください。',
    });
    expect(notify.update).toHaveBeenLastCalledWith(
      'notification:test',
      expect.objectContaining({
        status: 'progress',
        jobId: 'article-import-job:example',
        jobType: 'article-import',
      }),
    );
  });
});
