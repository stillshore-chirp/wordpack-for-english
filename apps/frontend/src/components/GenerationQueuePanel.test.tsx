import React, { useRef } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProviders } from '../main';
import { useNotifications } from '../NotificationsContext';
import { GenerationQueuePanel } from './GenerationQueuePanel';

const wordPackResponse = {
  lemma: 'alpha',
  sense_title: 'alpha概説',
  pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
  senses: [
    {
      id: 's1',
      gloss_ja: '意味',
      definition_ja: '定義',
      nuances_ja: 'ニュアンス',
      patterns: ['pattern'],
      synonyms: [],
      antonyms: [],
      register: 'neutral',
      notes_ja: null,
    },
  ],
  collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
  contrast: [],
  examples: {
    Dev: [],
    CS: [],
    LLM: [],
    Business: [],
    Common: [
      { en: 'Teams use alpha signals to compare early product ideas.', ja: 'チームは初期案を比べるためにalphaの合図を使います。', grammar_ja: '現在形' },
    ],
  },
  etymology: { note: '-', confidence: 'low' },
  study_card: 'alpha study card',
  citations: [],
  confidence: 'medium',
};

const setupFetchMocks = () => {
  const requestedUrls: string[] = [];
  vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    requestedUrls.push(url);
    if (url.endsWith('/api/config')) {
      return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/word/packs/wp:alpha')) {
      return new Response(JSON.stringify(wordPackResponse), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/word/packs/wp:alpha/regenerate/jobs/job-alpha')) {
      return new Response(JSON.stringify({
        job_id: 'job-alpha',
        status: 'succeeded',
        result: wordPackResponse,
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/word/lemma/alpha')) {
      return new Response(JSON.stringify({ found: true, id: 'wp:alpha', lemma: 'alpha', sense_title: 'alpha概説' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response(JSON.stringify({ detail: 'not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  });
  return requestedUrls;
};

const QueueHarness: React.FC = () => {
  const { add, update } = useNotifications();
  const notificationIdRef = useRef('n-alpha');
  return (
    <>
      <button
        type="button"
        onClick={() => {
          notificationIdRef.current = add({
            id: 'n-alpha',
            title: '【alpha】の生成処理中...',
            message: 'WordPackを生成しています',
            status: 'progress',
            wordPackId: 'wp:alpha',
            lemma: 'alpha',
          });
        }}
      >
        生成を開始
      </button>
      <button
        type="button"
        onClick={() => update(notificationIdRef.current, {
          title: '【alpha】の生成完了！',
          message: '生成が完了しました',
          status: 'success',
          wordPackId: 'wp:alpha',
          lemma: 'alpha',
        })}
      >
        生成を完了
      </button>
      <GenerationQueuePanel />
    </>
  );
};

const renderQueue = () => render(
  <AppProviders googleClientId="test-client">
    <QueueHarness />
  </AppProviders>,
);

describe('GenerationQueuePanel', () => {
  let requestedUrls: string[] = [];

  beforeEach(() => {
    requestedUrls = setupFetchMocks();
    try {
      localStorage.removeItem('wpfe.notifications.v1');
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
    } catch {}
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    try {
      localStorage.removeItem('wordpack.auth.v1');
      localStorage.removeItem('wpfe.notifications.v1');
    } catch {}
  });

  it('進行中と完了の更新カードだけ2秒間パルス表示する', async () => {
    const { container } = renderQueue();
    const startButton = await screen.findByRole('button', { name: '生成を開始' });
    await screen.findByRole('region', { name: '生成キュー' });
    await act(async () => {});

    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    await user.click(startButton);
    await act(async () => {});

    const progressCard = container.querySelector('.generation-queue-item');
    expect(progressCard).toHaveClass('is-updated');

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(progressCard).not.toHaveClass('is-updated');

    await user.click(screen.getByRole('button', { name: '生成を完了' }));
    await act(async () => {});
    const completedCard = screen.getByRole('button', { name: 'alpha の生成結果プレビューを開く' });
    expect(completedCard).toHaveClass('is-updated');

    act(() => {
      vi.advanceTimersByTime(2100);
    });
    expect(completedCard).not.toHaveClass('is-updated');
  });

  it('完了カードをクリックするとWordPackプレビューを開く', async () => {
    const user = userEvent.setup();
    renderQueue();

    await user.click(await screen.findByRole('button', { name: '生成を開始' }));
    await user.click(screen.getByRole('button', { name: '生成を完了' }));
    await user.click(screen.getByRole('button', { name: 'alpha の生成結果プレビューを開く' }));

    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /WordPack プレビュー: alpha/ })).toBeVisible();
    });
    await waitFor(() => {
      expect(requestedUrls.some((url) => url.endsWith('/api/word/packs/wp:alpha'))).toBe(true);
    });
  });

  it('古い進行中カードは保存済みWordPackを確認して完了へ補正する', async () => {
    const staleAt = Date.now() - 21 * 60 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-stale-alpha',
          title: '【alpha】の再生成ジョブ開始',
          message: 'バックグラウンドで再生成しています（完了までしばらくお待ちください）',
          status: 'progress',
          createdAt: staleAt,
          updatedAt: staleAt,
          model: 'gpt-5.6-luna',
          wordPackId: 'wp:alpha',
          lemma: 'alpha',
          jobId: 'job-alpha',
        },
      ]),
    );
    renderQueue();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'alpha の生成結果プレビューを開く' })).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: 'キューから隠す' })).not.toBeInTheDocument();
    expect(requestedUrls.some((url) => url.endsWith('/api/word/packs/wp:alpha/regenerate/jobs/job-alpha'))).toBe(true);
  });

  it('ジョブIDがない古い進行中カードは完了扱いしない', async () => {
    const staleAt = Date.now() - 21 * 60 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-stale-without-job',
          title: '【alpha】の再生成ジョブ開始',
          message: 'バックグラウンドで再生成しています（完了までしばらくお待ちください）',
          status: 'progress',
          createdAt: staleAt,
          updatedAt: staleAt,
          model: 'gpt-5.6-luna',
          wordPackId: 'wp:alpha',
          lemma: 'alpha',
        },
      ]),
    );
    renderQueue();

    await waitFor(() => {
      expect(screen.getAllByText(/ジョブIDが保存されていないため/).length).toBeGreaterThan(0);
    });
    expect(screen.queryByRole('button', { name: 'alpha の生成結果プレビューを開く' })).not.toBeInTheDocument();
  });
});
