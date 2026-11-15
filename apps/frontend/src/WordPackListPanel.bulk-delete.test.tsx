import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

describe('WordPackListPanel bulk delete', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try { sessionStorage.clear(); } catch {}
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
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {}
  });

  function renderWithAuth() {
    return render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );
  }

  function setupFetchMocks(options: { failFirstAlphaDelete?: boolean } = {}) {
    const createServerWordPack = (id: string, lemma: string) => ({
      id,
      lemma,
      sense_title: `${lemma.charAt(0).toUpperCase()}${lemma.slice(1)} overview`,
      created_at: '2026-01-01T00:00:00.000Z',
      updated_at: '2026-01-02T00:00:00.000Z',
    });
    const serverWordPacks = new Map([
      ['wp:test:alpha', createServerWordPack('wp:test:alpha', 'alpha')],
      ['wp:test:beta', createServerWordPack('wp:test:beta', 'beta')],
      ['wp:test:gamma', createServerWordPack('wp:test:gamma', 'gamma')],
    ]);
    const deleteAttempts = new Map<string, number>();
    const deleteRequests: string[] = [];
    let listRequests = 0;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';

      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        listRequests += 1;
        return new Response(
          JSON.stringify({
            items: [...serverWordPacks.values()],
            total: serverWordPacks.size,
            limit: 200,
            offset: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/word/packs/wp:test:') && method === 'DELETE') {
        const id = url.replace('/api/word/packs/', '');
        deleteRequests.push(id);
        const attempts = (deleteAttempts.get(id) ?? 0) + 1;
        deleteAttempts.set(id, attempts);
        if (options.failFirstAlphaDelete && id === 'wp:test:alpha' && attempts === 1) {
          return new Response(JSON.stringify({ detail: '一時的な削除エラー' }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        serverWordPacks.delete(id);
        return new Response(
          JSON.stringify({ message: 'deleted' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      return new Response('not found', { status: 404 });
    });
    return {
      fetchMock,
      serverWordPacks,
      deleteAttempts,
      deleteRequests,
      getListRequestCount: () => listRequests,
    };
  }

  it('allows selecting multiple WordPacks and deleting them together', async () => {
    const { fetchMock, serverWordPacks } = setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());

    const alphaCheckbox = await screen.findByRole('checkbox', { name: 'WordPack alpha を選択' });
    const betaCheckbox = await screen.findByRole('checkbox', { name: 'WordPack beta を選択' });
    expect(alphaCheckbox).not.toBeChecked();
    expect(betaCheckbox).not.toBeChecked();

    expect(screen.queryByRole('group', { name: 'WordPack選択操作' })).not.toBeInTheDocument();

    await act(async () => {
      await user.click(alphaCheckbox);
      await user.click(betaCheckbox);
    });

    expect(alphaCheckbox).toBeChecked();
    expect(betaCheckbox).toBeChecked();

    const selectionBar = await screen.findByRole('group', { name: 'WordPack選択操作' });
    const bulkDeleteButton = within(selectionBar).getByRole('button', { name: '削除' });
    expect(bulkDeleteButton).not.toBeDisabled();

    await act(async () => {
      await user.click(bulkDeleteButton);
    });

    expect(await screen.findByText(/実行後はこの画面から取り消せません/)).toBeInTheDocument();
    const confirmYes = await screen.findByRole('button', { name: '削除する' });
    await act(async () => {
      await user.click(confirmYes);
    });

    await waitFor(() => expect(screen.getByText('WordPackを2件削除しました')).toBeInTheDocument());

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/word/packs/wp:test:alpha',
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/word/packs/wp:test:beta',
      expect.objectContaining({ method: 'DELETE' }),
    );

    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(1));
    expect(screen.getAllByTestId('wp-card')[0]).toHaveTextContent('gamma');
    expect([...serverWordPacks.keys()]).toEqual(['wp:test:gamma']);
  });

  it('keeps selected WordPacks after a failed bulk delete and removes them on retry', async () => {
    const { serverWordPacks, deleteAttempts, deleteRequests, getListRequestCount } = setupFetchMocks({ failFirstAlphaDelete: true });
    renderWithAuth();
    const user = userEvent.setup();

    const alphaCheckbox = await screen.findByRole('checkbox', { name: 'WordPack alpha を選択' });
    const betaCheckbox = screen.getByRole('checkbox', { name: 'WordPack beta を選択' });
    await user.click(alphaCheckbox);
    await user.click(betaCheckbox);

    const selectionBar = screen.getByRole('group', { name: 'WordPack選択操作' });
    await user.click(within(selectionBar).getByRole('button', { name: '削除' }));
    await user.click(await screen.findByRole('button', { name: '削除する' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('WordPackの削除に失敗しました: 一時的な削除エラー');
    expect(getListRequestCount()).toBe(1);
    expect(serverWordPacks.size).toBe(3);
    expect(screen.getAllByTestId('wp-card')).toHaveLength(3);
    expect(alphaCheckbox).toBeChecked();
    expect(betaCheckbox).toBeChecked();
    expect(deleteRequests).toEqual(['wp:test:alpha']);

    const retryDeleteButton = within(screen.getByRole('group', { name: 'WordPack選択操作' })).getByRole('button', { name: '削除' });
    expect(retryDeleteButton).toBeEnabled();
    await user.click(retryDeleteButton);
    await user.click(await screen.findByRole('button', { name: '削除する' }));

    expect(await screen.findByText('WordPackを2件削除しました')).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByTestId('wp-card')).toHaveLength(1));
    expect(screen.getAllByTestId('wp-card')[0]).toHaveTextContent('gamma');
    expect(getListRequestCount()).toBe(2);
    expect([...serverWordPacks.keys()]).toEqual(['wp:test:gamma']);
    expect([...deleteAttempts.entries()]).toEqual([
      ['wp:test:alpha', 2],
      ['wp:test:beta', 1],
    ]);
    expect(deleteRequests).toEqual(['wp:test:alpha', 'wp:test:alpha', 'wp:test:beta']);
    expect(screen.queryByRole('group', { name: 'WordPack選択操作' })).not.toBeInTheDocument();
  });
});
