import { render, screen, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

const renderWithAuth = () =>
  render(
    <AppProviders googleClientId="test-client">
      <App />
    </AppProviders>,
  );

const setupGuestPublicFetch = () => {
  const guestPublicRequests: Array<{ guest_public: boolean }> = [];
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : (input as URL).toString();
    const method = init?.method ?? 'GET';

    if (url.endsWith('/api/config') && method === 'GET') {
      return new Response(
        JSON.stringify({ request_timeout_ms: 60000, llm_model: 'gpt-5.6-luna' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (url.startsWith('/api/word/packs?') && method === 'GET') {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'wp:alpha',
              lemma: 'alpha',
              sense_title: 'Alpha overview',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              is_empty: false,
              checked_only_count: 0,
              learned_count: 0,
              guest_public: false,
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (url.endsWith('/api/word/packs/wp:alpha/guest-public') && method === 'POST') {
      const body = init?.body ? JSON.parse(init.body as string) : {};
      guestPublicRequests.push(body);
      return new Response(
        JSON.stringify({ word_pack_id: 'wp:alpha', guest_public: body.guest_public }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  return { fetchMock, guestPublicRequests };
};

const createGuestPublicWordPack = (id: string, lemma: string, guestPublic = false) => ({
  id,
  lemma,
  sense_title: `${lemma} overview`,
  created_at: '2026-01-01T00:00:00.000Z',
  updated_at: '2026-01-02T00:00:00.000Z',
  is_empty: false,
  checked_only_count: 0,
  learned_count: 0,
  guest_public: guestPublic,
});

const setupBulkGuestPublicFetch = (deferFirstUpdateFailure = false) => {
  const serverWordPacks = new Map([
    ['wp:alpha', createGuestPublicWordPack('wp:alpha', 'alpha')],
    ['wp:beta', createGuestPublicWordPack('wp:beta', 'beta')],
  ]);
  const guestPublicRequests: Array<{ id: string; guest_public: boolean }> = [];
  let listRequests = 0;
  let resolveFirstFailure: ((response: Response) => void) | null = null;

  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : (input as URL).toString();
    const method = init?.method ?? 'GET';

    if (url.endsWith('/api/config') && method === 'GET') {
      return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    if (url.startsWith('/api/word/packs?') && method === 'GET') {
      listRequests += 1;
      return new Response(
        JSON.stringify({ items: [...serverWordPacks.values()], total: serverWordPacks.size, limit: 200, offset: 0 }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (url.includes('/api/word/packs/') && url.endsWith('/guest-public') && method === 'POST') {
      const id = url.match(/\/api\/word\/packs\/([^/]+)\/guest-public$/)?.[1] ?? '';
      const body = init?.body ? JSON.parse(init.body as string) : {};
      guestPublicRequests.push({ id, guest_public: body.guest_public });

      if (deferFirstUpdateFailure && guestPublicRequests.length === 1) {
        return new Promise<Response>((resolve) => {
          resolveFirstFailure = resolve;
        });
      }

      const current = serverWordPacks.get(id);
      if (!current) {
        return new Response(JSON.stringify({ detail: 'WordPackが見つかりません' }), {
          status: 404,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      serverWordPacks.set(id, { ...current, guest_public: body.guest_public });
      return new Response(JSON.stringify({ word_pack_id: id, guest_public: body.guest_public }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }

    return new Response(JSON.stringify({ detail: 'Not found' }), {
      status: 404,
      headers: { 'Content-Type': 'application/json' },
    });
  });

  return {
    fetchMock,
    guestPublicRequests,
    serverWordPacks,
    getListRequestCount: () => listRequests,
    rejectFirstUpdate(response: Response) {
      if (!resolveFirstFailure) throw new Error('First guest-public update is not pending');
      resolveFirstFailure(response);
      resolveFirstFailure = null;
    },
  };
};

const expectCardVisibility = (publicLemmas: string[]) => {
  const cards = screen.getAllByTestId('wp-card');
  expect(cards).toHaveLength(2);
  for (const card of cards) {
    const lemma = card.querySelector('.wp-card-title')?.textContent ?? '';
    within(card).getByText(publicLemmas.includes(lemma) ? '公開中' : '非公開');
  }
};

describe('WordPackListPanel guest public toggle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try {
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'sub', email: 'user@example.com', display_name: 'User' },
        }),
      );
    } catch {
      // localStorage が利用できない環境でもテストを継続する。
    }
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {
      // ignore
    }
  });

  it('sends guest public update request when toggled', async () => {
    const { guestPublicRequests } = setupGuestPublicFetch();
    renderWithAuth();

    const user = userEvent.setup();
    await waitFor(
      () => expect(screen.getByRole('button', { name: 'alpha のその他の操作' })).toBeInTheDocument(),
      { timeout: 5000 },
    );

    await user.click(screen.getByRole('button', { name: 'alpha のその他の操作' }));
    await user.click(screen.getByRole('menuitem', { name: 'ゲスト公開にする' }));

    await waitFor(() => expect(guestPublicRequests).toHaveLength(1));
    expect(guestPublicRequests[0]).toEqual({ guest_public: true });
  });

  it('publishes and unpublishes selected WordPacks, with server state reflected in the list', async () => {
    const { guestPublicRequests, serverWordPacks, getListRequestCount } = setupBulkGuestPublicFetch();
    renderWithAuth();
    const user = userEvent.setup();

    const alphaCheckbox = await screen.findByRole('checkbox', { name: 'WordPack alpha を選択' });
    const betaCheckbox = screen.getByRole('checkbox', { name: 'WordPack beta を選択' });
    await user.click(alphaCheckbox);
    await user.click(betaCheckbox);

    const selectionBar = screen.getByRole('group', { name: 'WordPack選択操作' });
    await user.click(within(selectionBar).getByRole('button', { name: '公開にする' }));

    await waitFor(() => expect(getListRequestCount()).toBe(2));
    expectCardVisibility(['alpha', 'beta']);
    expect(guestPublicRequests).toEqual([
      { id: 'wp:alpha', guest_public: true },
      { id: 'wp:beta', guest_public: true },
    ]);
    expect([...serverWordPacks.values()].every((wordPack) => wordPack.guest_public)).toBe(true);

    expectCardVisibility(['alpha', 'beta']);
    expect(alphaCheckbox).toBeChecked();
    expect(betaCheckbox).toBeChecked();

    await user.click(within(screen.getByRole('group', { name: 'WordPack選択操作' })).getByRole('button', { name: '非公開にする' }));

    await waitFor(() => expect(getListRequestCount()).toBe(3));
    expectCardVisibility([]);
    expect(guestPublicRequests.slice(2)).toEqual([
      { id: 'wp:alpha', guest_public: false },
      { id: 'wp:beta', guest_public: false },
    ]);
    expect([...serverWordPacks.values()].every((wordPack) => !wordPack.guest_public)).toBe(true);

    expectCardVisibility([]);
  });

  it('rolls back a failed bulk public update and allows retry', async () => {
    const { guestPublicRequests, serverWordPacks, getListRequestCount, rejectFirstUpdate } = setupBulkGuestPublicFetch(true);
    renderWithAuth();
    const user = userEvent.setup();

    const alphaCheckbox = await screen.findByRole('checkbox', { name: 'WordPack alpha を選択' });
    const betaCheckbox = screen.getByRole('checkbox', { name: 'WordPack beta を選択' });
    await user.click(alphaCheckbox);
    await user.click(betaCheckbox);
    await user.click(within(screen.getByRole('group', { name: 'WordPack選択操作' })).getByRole('button', { name: '公開にする' }));

    await waitFor(() => expect(guestPublicRequests).toHaveLength(1));
    expectCardVisibility(['alpha', 'beta']);

    rejectFirstUpdate(new Response(JSON.stringify({ detail: '一時的な公開設定エラー' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    }));

    expect(await screen.findByRole('alert')).toHaveTextContent('公開設定を0件更新しましたが一部失敗しました: 一時的な公開設定エラー');
    expectCardVisibility([]);
    expect([...serverWordPacks.values()].every((wordPack) => !wordPack.guest_public)).toBe(true);
    expect(alphaCheckbox).toBeChecked();
    expect(betaCheckbox).toBeChecked();

    const retryButton = within(screen.getByRole('group', { name: 'WordPack選択操作' })).getByRole('button', { name: '公開にする' });
    expect(retryButton).toBeEnabled();
    await user.click(retryButton);

    await waitFor(() => expect(getListRequestCount()).toBe(2));
    expectCardVisibility(['alpha', 'beta']);
    expect(guestPublicRequests.map(({ id, guest_public }) => [id, guest_public])).toEqual([
      ['wp:alpha', true],
      ['wp:alpha', true],
      ['wp:beta', true],
    ]);
    expect([...serverWordPacks.values()].every((wordPack) => wordPack.guest_public)).toBe(true);

    await waitFor(() => expect(getListRequestCount()).toBe(2));
    expectCardVisibility(['alpha', 'beta']);
  });
});
