import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';
import { ARTICLE_IMPORT_TEXT_MAX_LENGTH } from './constants/article';

describe('ArticleImportPanel model/params wiring (mocked fetch)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try {
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
    try { localStorage.removeItem('wordpack.auth.v1'); } catch {}
  });

  const renderWithAuth = () =>
    render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );

  function setupFetchMocks() {
    const mock = vi.spyOn(global, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      if (url.endsWith('/api/config') && (!init || (init && (!init.method || init.method === 'GET')))) {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } }
        );
      }
      if (url.endsWith('/api/article/import/jobs') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({
            job_id: 'article-import-job:test',
            status: 'succeeded',
            article_id: 'art:abcd1234',
          }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/article/generate_and_import') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({ lemma: 'test', word_pack_id: 'wp:test:abcd', category: 'Common', generated_examples: 2, article_ids: ['art:1', 'art:2'] }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/article/art:abcd1234') && (!init || (init && (!init.method || init.method === 'GET')))) {
        return new Response(
          JSON.stringify({
            id: 'art:abcd1234',
            title_en: 'Title',
            body_en: 'Body EN',
            body_ja: 'Body JA',
            llm_model: 'gpt-5.6-luna',
            llm_params: 'reasoning.effort=high;text.verbosity=medium',
            related_word_packs: [
              { word_pack_id: 'wp:regen:1', lemma: 'alpha', status: 'existing', is_empty: false },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/word/packs/wp:regen:1/regenerate/async') && init?.method === 'POST') {
        return new Response(
          JSON.stringify({ job_id: 'job:regen:1', status: 'succeeded' }),
          { status: 202, headers: { 'Content-Type': 'application/json' } },
        );
      }
      if (url.endsWith('/api/word/packs/wp:regen:1/regenerate/jobs/job:regen:1')) {
        return new Response(
          JSON.stringify({ job_id: 'job:regen:1', status: 'succeeded' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Response('not found', { status: 404 });
    });
    return mock;
  }

  const openTab = async (user: ReturnType<typeof userEvent.setup>, label: string) => {
    const toggle = screen.queryByRole('button', { name: 'メニューを開く' });
    if (toggle) {
      await act(async () => {
        await user.click(toggle);
      });
    }
    const tabButton = await screen.findByRole('button', { name: label });
    await act(async () => {
      await user.click(tabButton);
    });
  };

  const closeImportResult = async (user: ReturnType<typeof userEvent.setup>) => {
    const closeButton = await screen.findByRole('button', { name: 'インポート結果を閉じる' });
    await act(async () => {
      await user.click(closeButton);
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'インポート結果' })).not.toBeInTheDocument();
    });
  };

  it('sends reasoning/text_opts for the default model on import', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    // モデルUIが表示される
    const modelSelect = await screen.findByLabelText('モデル');
    await act(async () => {
      await user.selectOptions(modelSelect, 'gpt-5.6-luna');
    });

    const textarea = screen.getByPlaceholderText('文章を貼り付け（日本語/英語）');
    await act(async () => {
      await user.type(textarea, 'hello world');
      await user.click(screen.getByRole('button', { name: '文章をインポート' }));
    });

    // リクエスト検証
    const calls = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/import/jobs') : ((c[0] as URL).toString().endsWith('/api/article/import/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.some((b) => b.model === 'gpt-5.6-luna' && b.reasoning && b.text_opts && !('temperature' in b))).toBe(true);
  });

  it('sends reasoning/text_opts for gpt-5.6-luna on import, and reasoning/text on generate_and_import', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    // gpt-5.6-luna 選択で追加UIが表示
    const modelSelect = await screen.findByLabelText('モデル');
    await act(async () => {
      await user.selectOptions(modelSelect, 'gpt-5.6-luna');
    });
    expect(screen.getByLabelText('reasoning.effort')).toBeInTheDocument();
    expect(screen.getByLabelText('text.verbosity')).toBeInTheDocument();

    const textarea = screen.getByPlaceholderText('文章を貼り付け（日本語/英語）');
    await act(async () => {
      await user.type(textarea, 'hello world 2');
      await user.click(screen.getByRole('button', { name: '文章をインポート' }));
    });

    const importBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/import/jobs') : ((c[0] as URL).toString().endsWith('/api/article/import/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(importBodies.some((b) => b.model === 'gpt-5.6-luna' && b.reasoning && b.text_opts && !('temperature' in b))).toBe(true);

    // 例文生成・記事化でも同様のパラメータ（text キー）
    await closeImportResult(user);
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '例文を生成して記事化' }));
    });

    const genBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/generate_and_import') : ((c[0] as URL).toString().endsWith('/api/article/generate_and_import'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(genBodies.some((b) => b.model === 'gpt-5.6-luna' && b.reasoning && b.text && !('temperature' in b))).toBe(true);
  });

  it('sends selected generation_category in /api/article/import payload', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    // カテゴリ選択→インポート
    const devCategory = await screen.findByRole('checkbox', { name: /^Dev$/ });
    await act(async () => {
      await user.click(devCategory);
    });
    const textarea = screen.getByPlaceholderText('文章を貼り付け（日本語/英語）');
    await act(async () => {
      await user.type(textarea, 'hello cat');
      await user.click(screen.getByRole('button', { name: '文章をインポート' }));
    });

    const bodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/import/jobs') : ((c[0] as URL).toString().endsWith('/api/article/import/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(bodies.length).toBeGreaterThan(0);
    expect(bodies.some((b) => b.generation_category === 'Dev')).toBe(true);
  });

  it('disables import button and alerts when text length exceeds limit', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    const textarea = screen.getByPlaceholderText('文章を貼り付け（日本語/英語）');
    const overLimitText = 'あ'.repeat(ARTICLE_IMPORT_TEXT_MAX_LENGTH + 1);
    await act(async () => {
      fireEvent.change(textarea, { target: { value: overLimitText } });
    });

    const importButton = screen.getByRole('button', { name: '文章をインポート' });
    expect(importButton).toBeDisabled();
    const warning = screen.getByText(
      `文章は${ARTICLE_IMPORT_TEXT_MAX_LENGTH}文字以内で入力してください（現在 ${overLimitText.length} 文字）`,
    );
    expect(warning).toHaveAttribute('role', 'alert');

    const importBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/import/jobs') : ((c[0] as URL).toString().endsWith('/api/article/import/jobs'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(importBodies).toHaveLength(0);
  });

  it('sends the selected category when generating and importing examples', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    const commonCategory = await screen.findByRole('checkbox', { name: /^Common$/ });
    const devCategory = await screen.findByRole('checkbox', { name: /^Dev$/ });
    await act(async () => {
      await user.click(commonCategory);
      await user.click(devCategory);
    });
    expect((commonCategory as HTMLInputElement).checked).toBe(false);
    expect((devCategory as HTMLInputElement).checked).toBe(true);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '例文を生成して記事化' }));
    });

    const genBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/generate_and_import') : ((c[0] as URL).toString().endsWith('/api/article/generate_and_import'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(genBodies.length).toBeGreaterThan(0);
    expect(genBodies.some((b) => b.category === 'Dev')).toBe(true);
    expect(genBodies.every((b) => b.category !== 'Common')).toBe(true);
  });

  it('sends requests for every selected category when all is checked', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    const allCategories = await screen.findByRole('checkbox', { name: /^すべて$/ });
    await act(async () => {
      await user.click(allCategories);
      await user.click(screen.getByRole('button', { name: '例文を生成して記事化' }));
    });

    const genBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/article/generate_and_import') : ((c[0] as URL).toString().endsWith('/api/article/generate_and_import'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(genBodies.map((b) => b.category).sort()).toEqual(
      ['Business', 'CS', 'Common', 'Dev', 'LLM'].sort(),
    );
  });

  it('uses selected model for regenerate from import result modal (reasoning model)', async () => {
    const fetchMock = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');

    const modelSelect = await screen.findByLabelText('モデル');
    await act(async () => {
      await user.selectOptions(modelSelect, 'gpt-5.6-luna');
    });
    const textarea = screen.getByPlaceholderText('文章を貼り付け（日本語/英語）');
    await act(async () => {
      await user.type(textarea, 'hello regenerate');
      await user.click(screen.getByRole('button', { name: '文章をインポート' }));
    });

    const regenBtn = await screen.findByRole('button', { name: '例文を生成' });
    await act(async () => {
      await user.click(regenBtn);
    });

    const regenBodies = fetchMock.mock.calls
      .filter((c) => (typeof c[0] === 'string' ? (c[0] as string).endsWith('/api/word/packs/wp:regen:1/regenerate/async') : ((c[0] as URL).toString().endsWith('/api/word/packs/wp:regen:1/regenerate/async'))))
      .map((c) => (c[1]?.body ? JSON.parse(c[1]!.body as string) : {}));
    expect(regenBodies.some((b) => b.model === 'gpt-5.6-luna' && b.reasoning && b.text && !('temperature' in b))).toBe(true);
  });

});
