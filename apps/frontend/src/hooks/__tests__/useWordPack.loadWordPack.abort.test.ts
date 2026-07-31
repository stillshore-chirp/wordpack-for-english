import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWordPack, type WordPack } from '../useWordPack';
import type { Settings } from '../../SettingsContext';
import { ApiError, fetchJson } from '../../lib/fetcher';

const mockSettings = vi.hoisted(() => ({
  settings: {
    apiBase: '/api',
    pronunciationEnabled: true,
    regenerateScope: 'all',
    autoAdvanceAfterGrade: false,
    requestTimeoutMs: 30000,
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
  return {
    ...actual,
    fetchJson: vi.fn(),
  };
});

type Deferred<T> = {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
};

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function makeWordPack(lemma: string): WordPack {
  return {
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
    checked_only_count: 0,
    learned_count: 0,
  };
}

describe('useWordPack.loadWordPack', () => {
  beforeEach(() => {
    vi.mocked(fetchJson).mockReset();
    mockNotifications.add.mockClear();
    mockNotifications.update.mockClear();
  });

  it('aborts the previous request when loadWordPack is called again', async () => {
    const calls: Array<{ url: string; signal?: AbortSignal }> = [];
    const d1 = deferred<WordPack>();
    const d2 = deferred<WordPack>();

    vi.mocked(fetchJson).mockImplementation((url: any, options: any) => {
      const u = String(url);
      const signal: AbortSignal | undefined = options?.signal;
      calls.push({ url: u, signal });

      const d = u.endsWith('/word/packs/wp:1') ? d1 : u.endsWith('/word/packs/wp:2') ? d2 : deferred<WordPack>();
      if (signal) {
        if (signal.aborted) {
          d.reject(new ApiError('Request aborted or timed out', 0));
        } else {
          signal.addEventListener('abort', () => d.reject(new ApiError('Request aborted or timed out', 0)), { once: true });
        }
      }
      return d.promise as any;
    });

    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    let p1!: Promise<void>;
    act(() => {
      p1 = result.current.loadWordPack('wp:1');
    });

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe('/api/word/packs/wp:1');
    expect(calls[0].signal?.aborted).toBe(false);

    let p2!: Promise<void>;
    act(() => {
      p2 = result.current.loadWordPack('wp:2');
    });

    expect(calls).toHaveLength(2);
    expect(calls[1].url).toBe('/api/word/packs/wp:2');
    // 2回目の loadWordPack 開始時に、前の AbortController を中断できていること
    expect(calls[0].signal?.aborted).toBe(true);

    await act(async () => {
      d2.resolve(makeWordPack('produce'));
      await p2;
      await p1;
    });

    expect(result.current.currentWordPackId).toBe('wp:2');
    expect(result.current.data?.lemma).toBe('produce');
  });

  it('rejects invalid generated lemmas before starting network calls', async () => {
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.generateWordPack('This sentence, with punctuation.');
    });

    expect(fetchJson).not.toHaveBeenCalled();
    expect(mockNotifications.add).not.toHaveBeenCalled();
    expect(result.current.message).toEqual({
      kind: 'alert',
      text: '英数字と半角スペース、ハイフン、アポストロフィのみ利用できます',
    });
  });

  it('rejects invalid empty WordPack lemmas before starting network calls', async () => {
    const { result } = renderHook(() => useWordPack({ model: 'gpt-5.6-luna' }));

    await act(async () => {
      await result.current.createEmptyWordPack('文脈依存');
    });

    expect(fetchJson).not.toHaveBeenCalled();
    expect(mockNotifications.add).not.toHaveBeenCalled();
    expect(result.current.message).toEqual({
      kind: 'alert',
      text: '英数字と半角スペース、ハイフン、アポストロフィのみ利用できます',
    });
  });
});
