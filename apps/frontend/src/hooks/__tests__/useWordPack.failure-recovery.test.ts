import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useWordPack, type WordPack } from '../useWordPack';
import type { Settings } from '../../SettingsContext';
import { ApiError, fetchJson } from '../../lib/fetcher';
import {
  createWordPackGenerationJob,
  enqueueRegenerateWordPack,
  fetchRegenerateJobStatus,
  fetchWordPackGenerationJob,
} from '../../features/wordpack/api';
import type { WordPackGenerationJob } from '../../features/wordpack/api';

const mockSettings = vi.hoisted(() => ({
  settings: {
    apiBase: '/api',
    pronunciationEnabled: true,
    regenerateScope: 'all',
    autoAdvanceAfterGrade: false,
    requestTimeoutMs: 30_000,
    generationRequestTimeoutMs: 1_500_000,
    model: 'gpt-5.6-luna',
    reasoningEffort: 'high',
    textVerbosity: 'medium',
    theme: 'dark',
    ttsPlaybackRate: 1,
    ttsVolume: 1,
  } satisfies Settings,
}));

const mockNotifications = vi.hoisted(() => ({
  add: vi.fn(() => 'n-test'),
  update: vi.fn(),
  remove: vi.fn(),
  clearAll: vi.fn(),
  notifications: [],
}));

vi.mock('../../SettingsContext', () => ({
  DEFAULT_GENERATION_REQUEST_TIMEOUT_MS: 1_500_000,
  useSettings: () => mockSettings,
}));

vi.mock('../../NotificationsContext', () => ({
  useNotifications: () => mockNotifications,
}));

vi.mock('../../lib/fetcher', async () => {
  const actual = await vi.importActual<typeof import('../../lib/fetcher')>('../../lib/fetcher');
  return { ...actual, fetchJson: vi.fn() };
});

vi.mock('../../features/wordpack/api', () => ({
  composeModelRequestFields: vi.fn(() => ({})),
  createWordPackGenerationJob: vi.fn(),
  enqueueRegenerateWordPack: vi.fn(),
  fetchRegenerateJobStatus: vi.fn(),
  fetchWordPackGenerationJob: vi.fn(),
  updateGuestPublicFlag: vi.fn(),
}));

function makeWordPack(lemma: string, id?: string): WordPack {
  return {
    id,
    lemma,
    sense_title: lemma,
    pronunciation: { linking_notes: [] },
    senses: [],
    collocations: {
      general: { verb_object: [], adj_noun: [], prep_noun: [] },
      academic: { verb_object: [], adj_noun: [], prep_noun: [] },
    },
    contrast: [],
    examples: { Dev: [], CS: [], LLM: [], Business: [], Common: [] },
    etymology: { note: '', confidence: 'low' },
    study_card: '',
    citations: [],
    confidence: 'low',
  };
}

const mockedFetchJson = vi.mocked(fetchJson);
const mockedCreateGenerationJob = vi.mocked(createWordPackGenerationJob);
const mockedEnqueueRegenerate = vi.mocked(enqueueRegenerateWordPack);
const mockedFetchGenerationJob = vi.mocked(fetchWordPackGenerationJob);
const mockedFetchRegenerateStatus = vi.mocked(fetchRegenerateJobStatus);

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

describe('useWordPack failure recovery', () => {
  beforeEach(() => {
    mockedFetchJson.mockReset();
    mockedCreateGenerationJob.mockReset();
    mockedEnqueueRegenerate.mockReset();
    mockedFetchGenerationJob.mockReset();
    mockedFetchRegenerateStatus.mockReset();
    mockNotifications.add.mockClear();
    mockNotifications.update.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('reports a load failure and releases the loading state', async () => {
    mockedFetchJson.mockRejectedValueOnce(new ApiError('Service unavailable', 503));
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.loadWordPack('wp:load-failure');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(result.current.message).toEqual({ kind: 'alert', text: 'Service unavailable' });
  });

  it('clears the load error and exposes normalized data when retry succeeds', async () => {
    mockedFetchJson
      .mockRejectedValueOnce(new ApiError('Service unavailable', 503))
      .mockResolvedValueOnce(makeWordPack('recover'));
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.loadWordPack('wp:recover');
    });
    expect(result.current.message?.kind).toBe('alert');

    await act(async () => {
      await result.current.loadWordPack('wp:recover');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.message).toBeNull();
    expect(result.current.currentWordPackId).toBe('wp:recover');
    expect(result.current.data).toMatchObject({
      lemma: 'recover',
      checked_only_count: 0,
      learned_count: 0,
    });
  });

  it('shows a confirmed generation submission failure in the alert and notification', async () => {
    mockedCreateGenerationJob.mockRejectedValueOnce(new ApiError('Generation unavailable', 503));
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.generateWordPack('resilient');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(result.current.message).toEqual({ kind: 'alert', text: 'Generation unavailable' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'error',
      title: '【resilient】の生成失敗',
    }));
  });

  it('clears the generation error and publishes the result after retry succeeds', async () => {
    const generated = makeWordPack('resilient', 'wp:generated');
    mockedCreateGenerationJob
      .mockRejectedValueOnce(new ApiError('Generation unavailable', 503))
      .mockResolvedValueOnce({
        job_id: 'job:generated',
        job_type: 'wordpack-generation',
        status: 'succeeded',
        result: generated,
      });
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.generateWordPack('resilient');
    });
    expect(result.current.message?.kind).toBe('alert');

    await act(async () => {
      await result.current.generateWordPack('resilient');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data?.lemma).toBe('resilient');
    expect(result.current.message).toEqual({ kind: 'status', text: 'WordPack を生成しました' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'success',
      wordPackId: 'wp:generated',
    }));
  });

  it('keeps generation loading while queued and running polls finish, then publishes the result', async () => {
    const generated = makeWordPack('resilient', 'wp:generated');
    const completion = deferred<WordPackGenerationJob>();
    mockedCreateGenerationJob.mockResolvedValueOnce({
      job_id: 'job:generation-lifecycle',
      job_type: 'wordpack-generation',
      status: 'queued',
    });
    mockedFetchGenerationJob
      .mockResolvedValueOnce({
        job_id: 'job:generation-lifecycle',
        job_type: 'wordpack-generation',
        status: 'running',
      })
      .mockReturnValueOnce(completion.promise);
    vi.useFakeTimers();
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    let generation!: Promise<void>;
    act(() => {
      generation = result.current.generateWordPack('resilient');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(mockedFetchGenerationJob).toHaveBeenCalledTimes(2);

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.message).toBeNull();
    expect(mockNotifications.add).toHaveBeenCalledWith(expect.objectContaining({
      status: 'progress',
      lemma: 'resilient',
    }));
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      jobId: 'job:generation-lifecycle',
      pollingOwner: 'foreground',
    }));

    await act(async () => {
      completion.resolve({
        job_id: 'job:generation-lifecycle',
        job_type: 'wordpack-generation',
        status: 'succeeded',
        result: generated,
      });
      await generation;
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data?.lemma).toBe('resilient');
    expect(result.current.message).toEqual({ kind: 'status', text: 'WordPack を生成しました' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'success',
      wordPackId: 'wp:generated',
    }));
  });

  it('keeps the loaded WordPack visible when regeneration fails', async () => {
    mockedFetchJson.mockResolvedValueOnce(makeWordPack('existing', 'wp:existing'));
    mockedEnqueueRegenerate.mockResolvedValueOnce({
      job_id: 'job:regen',
      status: 'failed',
      error: 'Regeneration unavailable',
    });
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.loadWordPack('wp:existing');
    });
    const existingData = result.current.data;

    await act(async () => {
      await result.current.regenerateWordPack('wp:existing', 'existing');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBe(existingData);
    expect(result.current.message).toEqual({ kind: 'alert', text: 'Regeneration unavailable' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'error',
      message: 'Regeneration unavailable',
    }));
  });

  it('replaces retained data and clears the regeneration error after retry succeeds', async () => {
    mockedFetchJson.mockResolvedValueOnce(makeWordPack('existing', 'wp:existing'));
    mockedEnqueueRegenerate
      .mockResolvedValueOnce({
        job_id: 'job:regen-failed',
        status: 'failed',
        error: 'Regeneration unavailable',
      })
      .mockResolvedValueOnce({
        job_id: 'job:regen-success',
        status: 'succeeded',
        result: makeWordPack('existing', 'wp:existing'),
      });
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.loadWordPack('wp:existing');
    });
    const existingData = result.current.data;
    await act(async () => {
      await result.current.regenerateWordPack('wp:existing', 'existing');
    });
    expect(result.current.data).toBe(existingData);
    expect(result.current.message?.kind).toBe('alert');

    await act(async () => {
      await result.current.regenerateWordPack('wp:existing', 'existing');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).not.toBe(existingData);
    expect(result.current.message).toEqual({ kind: 'status', text: 'WordPackを再生成しました' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'success',
      jobId: 'job:regen-success',
    }));
  });

  it('retains the current WordPack during regeneration polling and replaces it on completion', async () => {
    const completed = deferred<{ job_id: string; status: 'succeeded'; result: WordPack }>();
    const regenerated = makeWordPack('existing', 'wp:existing');
    mockedFetchJson.mockResolvedValueOnce(makeWordPack('existing', 'wp:existing'));
    mockedEnqueueRegenerate.mockResolvedValueOnce({
      job_id: 'job:regeneration-lifecycle',
      status: 'pending',
    });
    mockedFetchRegenerateStatus
      .mockResolvedValueOnce({
        job_id: 'job:regeneration-lifecycle',
        status: 'running',
      })
      .mockReturnValueOnce(completed.promise);
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.loadWordPack('wp:existing');
    });
    const existingData = result.current.data;
    vi.useFakeTimers();
    let regeneration!: Promise<void>;
    act(() => {
      regeneration = result.current.regenerateWordPack('wp:existing', 'existing');
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3_000);
    });
    expect(mockedFetchRegenerateStatus).toHaveBeenCalledTimes(2);

    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBe(existingData);
    expect(result.current.message).toBeNull();
    expect(mockNotifications.add).toHaveBeenLastCalledWith(expect.objectContaining({
      status: 'progress',
      wordPackId: 'wp:existing',
    }));

    await act(async () => {
      completed.resolve({
        job_id: 'job:regeneration-lifecycle',
        status: 'succeeded',
        result: regenerated,
      });
      await regeneration;
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.data).not.toBe(existingData);
    expect(result.current.data?.lemma).toBe('existing');
    expect(result.current.message).toEqual({ kind: 'status', text: 'WordPackを再生成しました' });
    expect(mockNotifications.update).toHaveBeenLastCalledWith('n-test', expect.objectContaining({
      status: 'success',
      jobId: 'job:regeneration-lifecycle',
    }));
  });
});
