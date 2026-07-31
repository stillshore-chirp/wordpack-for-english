import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  createArticleImportJob,
  fetchArticleImportJob,
} from '../../features/article-import/api/articleApi';
import type { WordPack } from '../useWordPack';
import { useExampleActions } from '../useExampleActions';
import {
  createExampleGenerationJob,
  fetchExampleGenerationJob,
} from '../../features/generation/api';
import { ApiError } from '../../shared/api/ApiError';

vi.mock('../../features/article-import/api/articleApi', () => ({
  createArticleImportJob: vi.fn(),
  fetchArticleImportJob: vi.fn(),
}));
vi.mock('../../features/generation/api', () => ({
  createExampleGenerationJob: vi.fn(),
  fetchExampleGenerationJob: vi.fn(),
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
      kind: 'status',
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

describe('useExampleActions.generateExamples', () => {
  const notify = {
    add: vi.fn(() => 'notification:example-generation'),
    update: vi.fn(),
  };
  const setStatusMessage = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    notify.add.mockClear();
    notify.update.mockClear();
    setStatusMessage.mockClear();
    vi.mocked(createExampleGenerationJob).mockResolvedValue({
      job_id: 'example-generation-job:test',
      job_type: 'example-generation',
      status: 'running',
    });
    vi.mocked(fetchExampleGenerationJob).mockRejectedValue(
      new Error('status temporarily unavailable'),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('ジョブ受付後の状態取得失敗を生成キューで再照合できる進行中状態に保つ', async () => {
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
      const generationPromise = result.current.generateExamples('Dev');
      await vi.advanceTimersByTimeAsync(1000);
      await generationPromise;
    });

    expect(setStatusMessage).toHaveBeenLastCalledWith({
      kind: 'status',
      text: '例文の追加生成はバックグラウンドで継続しています。生成キューから状態を確認してください。',
    });
    expect(notify.update).toHaveBeenLastCalledWith(
      'notification:example-generation',
      expect.objectContaining({
        status: 'progress',
        jobId: 'example-generation-job:test',
        jobType: 'example-generation',
      }),
    );
  });

  it('202応答喪失時は送信した同じ例文生成ジョブIDを生成キューへ引き継ぐ', async () => {
    vi.mocked(createExampleGenerationJob).mockRejectedValueOnce(
      new ApiError('Network error', 0),
    );
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
      await result.current.generateExamples('Dev');
    });

    const clientJobId = vi.mocked(createExampleGenerationJob).mock.calls[0]?.[4];
    expect(clientJobId).toMatch(/^[0-9a-f-]{36}$/);
    expect(setStatusMessage).toHaveBeenLastCalledWith({
      kind: 'status',
      text: '例文の追加生成の送信結果を確認中です。生成キューが同じIDで受理状況を再確認します。',
    });
    expect(notify.update).toHaveBeenLastCalledWith(
      'notification:example-generation',
      expect.objectContaining({
        status: 'progress',
        jobId: `example-generation-job:${clientJobId}`,
        jobType: 'example-generation',
      }),
    );
  });
});
