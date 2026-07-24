import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

const wordPacks = [
  {
    id: 'wp:state:alpha',
    lemma: 'alpha',
    sense_title: '状態確認用のWordPack',
    created_at: '2024-01-10T09:15:00Z',
    updated_at: '2024-01-12T12:00:00Z',
    is_empty: false,
    guest_public: false,
    examples_count: { Dev: 2, CS: 0, LLM: 0, Business: 0, Common: 1 },
    checked_only_count: 1,
    learned_count: 2,
  },
  {
    id: 'wp:state:bravo',
    lemma: 'bravo',
    sense_title: '状態確認用のWordPack',
    created_at: '2024-01-08T08:30:00Z',
    updated_at: '2024-01-11T18:05:00Z',
    is_empty: false,
    guest_public: false,
    examples_count: { Dev: 1, CS: 0, LLM: 0, Business: 0, Common: 0 },
    checked_only_count: 0,
    learned_count: 0,
  },
];

const listResponse = (items = wordPacks) =>
  new Response(
    JSON.stringify({
      items,
      total: items.length,
      limit: 200,
      offset: 0,
    }),
    { status: 200, headers: { 'Content-Type': 'application/json' } },
  );

const errorResponse = () =>
  new Response(
    JSON.stringify({ detail: '一時的にWordPack一覧を取得できません。' }),
    { status: 503, headers: { 'Content-Type': 'application/json' } },
  );

const renderWithAuth = () =>
  render(
    <AppProviders googleClientId="test-client">
      <App />
    </AppProviders>,
  );

const setupFetch = (
  listHandler: (requestIndex: number) => Promise<Response> | Response,
) => {
  let requestIndex = 0;
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = init?.method ?? 'GET';

    if (url.endsWith('/api/config') && method === 'GET') {
      return new Response(
        JSON.stringify({ request_timeout_ms: 60000, llm_model: 'gpt-5.4-mini' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.startsWith('/api/word/packs?') && method === 'GET') {
      requestIndex += 1;
      return listHandler(requestIndex);
    }
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
};

describe('WordPackListPanel list states', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    sessionStorage.clear();
    localStorage.setItem(
      'wordpack.auth.v1',
      JSON.stringify({
        authMode: 'authenticated',
        user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
      }),
    );
  });

  afterEach(() => {
    localStorage.removeItem('wordpack.auth.v1');
  });

  it('初回読み込み中を空状態と区別する', async () => {
    let resolveInitialLoad: ((response: Response) => void) | null = null;
    const pendingInitialLoad = new Promise<Response>((resolve) => {
      resolveInitialLoad = resolve;
    });
    setupFetch(() => pendingInitialLoad);
    renderWithAuth();

    expect(await screen.findByText('WordPack一覧を読み込み中')).toBeInTheDocument();
    expect(screen.getByLabelText('件数を確認中')).toHaveTextContent('確認中');
    expect(screen.queryByRole('heading', { name: '保存済みWordPackはまだありません' })).not.toBeInTheDocument();

    await act(async () => {
      resolveInitialLoad?.(listResponse());
      await pendingInitialLoad;
    });
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
  });

  it('初回空状態から新規作成入力へ移動できる', async () => {
    setupFetch(() => listResponse([]));
    renderWithAuth();
    const user = userEvent.setup();

    const heading = await screen.findByRole('heading', { name: '保存済みWordPackはまだありません' });
    const state = heading.closest('section');
    expect(state).not.toBeNull();
    expect(within(state!).getByRole('status')).toHaveTextContent(
      '見出し語を登録すると、ここから内容を確認・管理できます。',
    );
    expect(screen.queryByText('保存済みのWordPackがありません。')).not.toBeInTheDocument();

    const createInput = await screen.findByRole('textbox', { name: '見出し語' });
    await user.click(within(state!).getByRole('button', { name: '新しいWordPackを作成' }));
    expect(createInput).toHaveFocus();
  });

  it('ゲストの空状態に作成操作を表示しない', async () => {
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    setupFetch(() => listResponse([]));
    renderWithAuth();

    const heading = await screen.findByRole('heading', { name: '公開中のWordPackはまだありません' });
    const state = heading.closest('section');
    expect(state).not.toBeNull();
    expect(within(state!).getByRole('status')).toHaveTextContent(
      '公開されたWordPackが追加されると、ここで閲覧できます。',
    );
    expect(within(state!).queryByRole('button', { name: '新しいWordPackを作成' })).not.toBeInTheDocument();
  });

  it('検索結果0件と絞り込み結果0件に条件と解除操作を示す', async () => {
    setupFetch(() => listResponse());
    renderWithAuth();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
    const searchInput = screen.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await user.clear(searchInput);
    await user.type(searchInput, 'no-match{Enter}');

    let heading = await screen.findByRole('heading', { name: '検索条件に一致するWordPackがありません' });
    let state = heading.closest('section');
    expect(within(state!).getByRole('status')).toHaveTextContent('保存済みのWordPackは残っています。');
    expect(screen.queryByRole('heading', { name: '最近開いたWordPack' })).not.toBeInTheDocument();
    expect(within(state!).getByRole('list', { name: '現在適用中の条件' })).toHaveTextContent(
      '検索: no-match（部分一致）',
    );
    await user.click(within(state!).getByRole('button', { name: '検索を解除' }));
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
    expect(searchInput).toHaveValue('');

    await user.click(screen.getByRole('button', { name: '公開中 0' }));
    heading = await screen.findByRole('heading', { name: '絞り込み条件に一致するWordPackがありません' });
    state = heading.closest('section');
    expect(within(state!).getByRole('list', { name: '現在適用中の条件' })).toHaveTextContent(
      '公開状態: 公開中',
    );
    await user.click(within(state!).getByRole('button', { name: '絞り込みを解除' }));
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
  });

  it('初回読み込み失敗を空状態と混同せず再試行できる', async () => {
    setupFetch((requestIndex) => requestIndex === 1 ? errorResponse() : listResponse());
    renderWithAuth();
    const user = userEvent.setup();

    const heading = await screen.findByRole('heading', { name: 'WordPack一覧を読み込めませんでした' });
    const state = heading.closest('section');
    const alert = within(state!).getByRole('alert');
    expect(alert).toHaveTextContent('保存済みデータが削除されたわけではありません。');
    expect(alert).toHaveTextContent('一時的にWordPack一覧を取得できません。');
    expect(screen.getByLabelText('件数を取得できませんでした')).toHaveTextContent('未取得');
    expect(screen.queryByRole('heading', { name: '保存済みWordPackはまだありません' })).not.toBeInTheDocument();

    await user.click(within(state!).getByRole('button', { name: 'もう一度読み込む' }));
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
    expect(screen.queryByRole('heading', { name: 'WordPack一覧を読み込めませんでした' })).not.toBeInTheDocument();
  });

  it('再読み込み中と失敗後も前回取得した一覧を保持する', async () => {
    let resolveRefresh: ((response: Response) => void) | null = null;
    const pendingRefresh = new Promise<Response>((resolve) => {
      resolveRefresh = resolve;
    });
    setupFetch((requestIndex) => requestIndex === 1 ? listResponse() : pendingRefresh);
    renderWithAuth();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(2));
    await user.click(screen.getByRole('button', { name: '更新' }));

    expect(await screen.findByText('WordPack一覧を更新中')).toBeInTheDocument();
    expect(screen.getAllByTestId('wp-card')).toHaveLength(2);

    await act(async () => {
      resolveRefresh?.(errorResponse());
      await pendingRefresh;
    });

    const heading = await screen.findByRole('heading', { name: '最新の一覧に更新できませんでした' });
    const state = heading.closest('section');
    expect(within(state!).getByRole('alert')).toHaveTextContent(
      '前回取得したWordPackを表示しています。画面上の内容は最新でない可能性があります。',
    );
    expect(screen.getAllByTestId('wp-card')).toHaveLength(2);
  });
});
