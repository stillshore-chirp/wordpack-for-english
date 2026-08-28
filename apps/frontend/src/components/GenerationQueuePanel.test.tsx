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
    if (url.endsWith('/api/word/packs/wp:alpha/regenerate/jobs/job-running')) {
      return new Response(JSON.stringify({
        job_id: 'job-running',
        status: 'running',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/word/pack/jobs/wordpack-generation-job%3Aalpha')) {
      return new Response(JSON.stringify({
        job_id: 'wordpack-generation-job:alpha',
        job_type: 'wordpack-generation',
        status: 'succeeded',
        result: {
          id: 'wp:alpha',
          ...wordPackResponse,
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/article/import/jobs/article-import-job%3Aalpha')) {
      return new Response(JSON.stringify({
        job_id: 'article-import-job:alpha',
        status: 'succeeded',
        article_id: 'art:alpha',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/quiz/generate/jobs/quiz-job%3Aalpha')) {
      return new Response(JSON.stringify({
        job_id: 'quiz-job:alpha',
        status: 'succeeded',
        quiz_id: 'quiz:alpha',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/quiz/generate/jobs/quiz-job%3Aretry')) {
      return new Response(JSON.stringify({
        job_id: 'quiz-job:retry',
        status: 'running',
        attempt_count: 3,
        attempt_limit: 5,
        retry_phase: 'translation_alignment',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/quiz/generate/jobs/quiz-job%3Afailed')) {
      return new Response(JSON.stringify({
        job_id: 'quiz-job:failed',
        status: 'failed',
        error_code: 'QUIZ_TRANSLATION_ALIGNMENT_FAILED',
        error: '英文と日本語訳の文対応を確認できなかったため、5回試行後にQuiz生成を停止しました。時間をおいてもう一度生成してください。',
        attempt_count: 5,
        attempt_limit: 5,
        retry_phase: 'translation_alignment',
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/article/generate_and_import/jobs/category-job%3Aalpha')) {
      return new Response(JSON.stringify({
        job_id: 'category-job:alpha',
        job_type: 'category-generate-import',
        status: 'succeeded',
        result: {
          lemma: 'alpha',
          word_pack_id: 'wp:alpha',
          category: 'Dev',
          generated_examples: 2,
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/api/word/packs/wp%3Aalpha/examples/Dev/generate/jobs/example-job%3Aalpha')) {
      return new Response(JSON.stringify({
        job_id: 'example-job:alpha',
        job_type: 'example-generation',
        status: 'succeeded',
        result: {
          word_pack_id: 'wp:alpha',
          lemma: 'alpha',
          category: 'Dev',
          added: 2,
        },
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
      <button
        type="button"
        onClick={() => {
          notificationIdRef.current = add({
            id: 'n-foreground-category',
            title: '【Dev】の例文生成・記事化を開始します',
            message: '前景画面が状態を確認しています',
            status: 'progress',
            model: 'gpt-5.6-luna',
            category: 'Dev',
            jobId: 'category-job:alpha',
            jobType: 'category-generate-import',
            pollingOwner: 'foreground',
          });
        }}
      >
        前景ポーリングを開始
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

  it('ジョブIDがない進行中カードは同期処理として期限切れ補正しない', async () => {
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

    expect(await screen.findByRole('button', { name: 'キューから隠す' })).toBeInTheDocument();
    expect(screen.queryByText(/ジョブIDが保存されていないため/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'alpha の生成結果プレビューを開く' })).not.toBeInTheDocument();
  });

  it('全体上限を越えた文章インポートジョブは状態APIから完了へ補正する', async () => {
    const articleUpdated = vi.fn();
    window.addEventListener('article:updated', articleUpdated);
    const staleAt = Date.now() - 27 * 60 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-stale-article',
          title: '文章インポート中...',
          message: 'バックグラウンドで文章を処理しています',
          status: 'progress',
          createdAt: staleAt,
          updatedAt: staleAt,
          model: 'gpt-5.6-luna',
          jobId: 'article-import-job:alpha',
          jobType: 'article-import',
        },
      ]),
    );
    renderQueue();

    expect(await screen.findByText('文章インポート完了')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('保存済み記事を確認しました');
    });
    expect(
      requestedUrls.some((url) => url.endsWith('/api/article/import/jobs/article-import-job%3Aalpha')),
    ).toBe(true);
    expect(articleUpdated).toHaveBeenCalledOnce();
    window.removeEventListener('article:updated', articleUpdated);
  });

  it('再読込後の文章インポートジョブは全体上限を待たずに状態確認を再開する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-restored-article',
          title: '文章インポート中...',
          message: 'バックグラウンドで文章を処理しています',
          status: 'progress',
          createdAt: persistedAt,
          updatedAt: persistedAt,
          model: 'gpt-5.6-luna',
          jobId: 'article-import-job:alpha',
          jobType: 'article-import',
        },
      ]),
    );
    renderQueue();

    expect(await screen.findByText('文章インポート完了')).toBeInTheDocument();
    expect(
      requestedUrls.some((url) => url.endsWith('/api/article/import/jobs/article-import-job%3Aalpha')),
    ).toBe(true);
  });

  it('再読込後のQuiz生成ジョブは状態APIから完了へ補正する', async () => {
    const quizUpdated = vi.fn();
    window.addEventListener('quiz:updated', quizUpdated);
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-restored-quiz',
          title: 'Quiz生成中',
          message: '生成はサーバーで継続中です',
          status: 'progress',
          createdAt: persistedAt,
          updatedAt: persistedAt,
          model: 'gpt-5.6-luna',
          jobId: 'quiz-job:alpha',
          jobType: 'quiz-generation',
        },
      ]),
    );
    renderQueue();

    expect(await screen.findByText('Quiz生成完了')).toBeInTheDocument();
    expect(
      requestedUrls.some((url) => url.endsWith('/api/quiz/generate/jobs/quiz-job%3Aalpha')),
    ).toBe(true);
    expect(quizUpdated).toHaveBeenCalledOnce();
    window.removeEventListener('quiz:updated', quizUpdated);
  });

  it('再読込後のQuiz生成ジョブへ文対応の再試行状況を反映する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([{
        id: 'n-restored-quiz-retry',
        title: 'Quiz生成中',
        message: '生成はサーバーで継続中です',
        status: 'progress',
        createdAt: persistedAt,
        updatedAt: persistedAt,
        model: 'gpt-5.6-luna',
        jobId: 'quiz-job:retry',
        jobType: 'quiz-generation',
      }]),
    );
    renderQueue();

    expect(await screen.findByText('文対応を再確認しています（3/5）')).toBeInTheDocument();
    await waitFor(() => {
      const persisted = JSON.parse(localStorage.getItem('wpfe.notifications.v1') || '[]');
      expect(persisted[0]).toMatchObject({
        attemptCount: 3,
        attemptLimit: 5,
        retryPhase: 'translation_alignment',
      });
    });
  });

  it('5回目の文対応失敗を利用者向けメッセージで表示する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([{
        id: 'n-restored-quiz-failed',
        title: 'Quiz生成中',
        message: '生成はサーバーで継続中です',
        status: 'progress',
        createdAt: persistedAt,
        updatedAt: persistedAt,
        model: 'gpt-5.6-luna',
        jobId: 'quiz-job:failed',
        jobType: 'quiz-generation',
      }]),
    );
    renderQueue();

    expect(await screen.findByText(/5回試行後にQuiz生成を停止しました/)).toBeInTheDocument();
    expect(screen.getByText('Quiz生成失敗')).toBeInTheDocument();
  });

  it('再読込後のカテゴリ生成・記事化ジョブはWordPackと記事を更新する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([{
        id: 'n-restored-category',
        title: '【Dev】の例文生成・記事化を開始します',
        message: 'バックグラウンドで生成しています',
        status: 'progress',
        createdAt: persistedAt,
        updatedAt: persistedAt,
        model: 'gpt-5.6-luna',
        category: 'Dev',
        jobId: 'category-job:alpha',
        jobType: 'category-generate-import',
      }]),
    );
    renderQueue();

    expect(await screen.findByRole('button', { name: 'alpha の生成結果プレビューを開く' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('2件の例文から記事を作成しました');
    });
    expect(
      requestedUrls.some((url) => url.endsWith('/api/article/generate_and_import/jobs/category-job%3Aalpha')),
    ).toBe(true);
  });

  it('再読込後の新規WordPack生成ジョブは完了カードへ補正する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([{
        id: 'n-restored-wordpack-generation',
        title: '【alpha】の生成処理中...',
        message: 'バックグラウンドで生成しています',
        status: 'progress',
        createdAt: persistedAt,
        updatedAt: persistedAt,
        model: 'gpt-5.6-luna',
        lemma: 'alpha',
        jobId: 'wordpack-generation-job:alpha',
        jobType: 'wordpack-generation',
      }]),
    );
    renderQueue();

    expect(await screen.findByRole('button', { name: 'alpha の生成結果プレビューを開く' })).toBeInTheDocument();
    expect(
      requestedUrls.some((url) => url.endsWith('/api/word/pack/jobs/wordpack-generation-job%3Aalpha')),
    ).toBe(true);
  });

  it('再読込後の追加例文生成ジョブはWordPackの完了カードへ補正する', async () => {
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([{
        id: 'n-restored-example',
        title: '【alpha】の生成処理中...',
        message: '例文をバックグラウンドで追加生成しています',
        status: 'progress',
        createdAt: persistedAt,
        updatedAt: persistedAt,
        model: 'gpt-5.6-luna',
        category: 'Dev',
        wordPackId: 'wp:alpha',
        lemma: 'alpha',
        jobId: 'example-job:alpha',
        jobType: 'example-generation',
      }]),
    );
    renderQueue();

    expect(await screen.findByRole('button', { name: 'alpha の生成結果プレビューを開く' })).toBeInTheDocument();
    expect(
      requestedUrls.some((url) => url.endsWith('/api/word/packs/wp%3Aalpha/examples/Dev/generate/jobs/example-job%3Aalpha')),
    ).toBe(true);
  });

  it('状態確認が未完了の間は同じジョブを重複pollしない', async () => {
    vi.useFakeTimers();
    const persistedAt = Date.now() - 10 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-slow-article',
          title: '文章インポート中...',
          message: 'バックグラウンドで文章を処理しています',
          status: 'progress',
          createdAt: persistedAt,
          updatedAt: persistedAt,
          model: 'gpt-5.6-luna',
          jobId: 'article-import-job:slow',
          jobType: 'article-import',
        },
      ]),
    );
    const fetchMock = vi.mocked(global.fetch);
    const baseImplementation = fetchMock.getMockImplementation();
    let statusRequestCount = 0;
    const statusRequestResolvers: Array<(response: Response) => void> = [];
    fetchMock.mockImplementation((input, init) => {
      const url = typeof input === 'string' ? input : input.toString();
      if (url.endsWith('/api/article/import/jobs/article-import-job%3Aslow')) {
        statusRequestCount += 1;
        return new Promise<Response>((resolve) => {
          statusRequestResolvers.push(resolve);
        });
      }
      if (!baseImplementation) throw new Error('fetch mock is unavailable');
      return baseImplementation(input, init);
    });

    renderQueue();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(statusRequestCount).toBe(1);
    statusRequestResolvers[0]?.(new Response(JSON.stringify({
      job_id: 'article-import-job:slow',
      status: 'running',
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    await act(async () => {});
  });

  it('前景ポーラーの実行中は復旧pollを重ねず再読込後に引き継ぐ', async () => {
    const rendered = renderQueue();
    await screen.findByRole('region', { name: '生成キュー' });
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    await user.click(screen.getByRole('button', { name: '前景ポーリングを開始' }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    const statusPath = '/api/article/generate_and_import/jobs/category-job%3Aalpha';
    expect(requestedUrls.some((url) => url.endsWith(statusPath))).toBe(false);
    const persisted = JSON.parse(localStorage.getItem('wpfe.notifications.v1') || '[]');
    expect(persisted[0]).not.toHaveProperty('pollingOwner');

    rendered.unmount();
    renderQueue();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(requestedUrls.some((url) => url.endsWith(statusPath))).toBe(true);
  });

  it('生成上限内でrunningのWordPackジョブは失敗扱いにしない', async () => {
    const startedAt = Date.now() - 21 * 60 * 1000;
    localStorage.setItem(
      'wpfe.notifications.v1',
      JSON.stringify([
        {
          id: 'n-running-alpha',
          title: '【alpha】の再生成ジョブ開始',
          message: 'バックグラウンドで再生成しています',
          status: 'progress',
          createdAt: startedAt,
          updatedAt: startedAt,
          model: 'gpt-5.6-luna',
          wordPackId: 'wp:alpha',
          lemma: 'alpha',
          jobId: 'job-running',
        },
      ]),
    );
    renderQueue();

    await waitFor(() => {
      expect(
        requestedUrls.some((url) => url.endsWith('/api/word/packs/wp:alpha/regenerate/jobs/job-running')),
      ).toBe(true);
    });
    expect(screen.getByRole('button', { name: 'キューから隠す' })).toBeInTheDocument();
    expect(screen.queryByText(/生成状態を確認できません/)).not.toBeInTheDocument();
  });
});
