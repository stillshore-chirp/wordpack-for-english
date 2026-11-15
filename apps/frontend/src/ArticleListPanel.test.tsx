import { render, screen, waitFor, act, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';
import type { ArticleDetailData } from './components/ArticleDetailModal';

describe('ArticleListPanel bulk delete', () => {
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
    try { localStorage.removeItem('wordpack.auth.v1'); } catch {}
  });

  const renderWithAuth = () =>
    render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );

  function setupFetchMocks({
    failFirstDelete = false,
    failFirstGuestPublic = false,
  }: { failFirstDelete?: boolean; failFirstGuestPublic?: boolean } = {}) {
    let shouldFailNextDelete = failFirstDelete;
    let shouldFailNextGuestPublic = failFirstGuestPublic;
    const deletedIds = new Set<string>();
    const deleteRequests: string[] = [];
    const guestPublicRequests: Array<{ articleId: string; guestPublic: boolean }> = [];
    const baseItems = [
      {
        id: 'article-1',
        title_en: 'First article',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        guest_public: false,
      },
      {
        id: 'article-2',
        title_en: 'Second article',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        guest_public: false,
      },
      {
        id: 'article-3',
        title_en: 'Third article',
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        guest_public: false,
      },
    ];
    const serverGuestPublic = new Map<string, boolean>(
      baseItems.map(({ id }) => [id, false] as const),
    );
    let releaseFirstGuestPublicFailure!: (response: Response) => void;
    const firstGuestPublicFailure = new Promise<Response>((resolve) => {
      releaseFirstGuestPublicFailure = resolve;
    });
    const mock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';

      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/article?') && method === 'GET') {
        const items = baseItems
          .filter(({ id }) => !deletedIds.has(id))
          .map((item) => ({ ...item, guest_public: serverGuestPublic.get(item.id) ?? false }));
        return new Response(
          JSON.stringify({ items, total: items.length, limit: 20, offset: 0 }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/article/') && method === 'GET') {
        const articleId = url.slice('/api/article/'.length);
        const item = baseItems.find(({ id }) => id === articleId);
        if (!item) return new Response('not found', { status: 404 });
        const detail: ArticleDetailData = {
          id: item.id,
          title_en: item.title_en,
          body_en: 'Review this article before sharing.',
          body_ja: '共有する前にこの記事を確認してください。',
          related_word_packs: [],
          guest_public: serverGuestPublic.get(item.id) ?? false,
        };
        return new Response(JSON.stringify(detail), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.startsWith('/api/article/') && url.endsWith('/guest-public') && method === 'POST') {
        const articleId = url.slice('/api/article/'.length, -'/guest-public'.length);
        const body = JSON.parse(String(init?.body ?? '{}')) as { guest_public: boolean };
        guestPublicRequests.push({ articleId, guestPublic: body.guest_public });
        if (shouldFailNextGuestPublic) {
          shouldFailNextGuestPublic = false;
          return firstGuestPublicFailure;
        }
        serverGuestPublic.set(articleId, body.guest_public);
        return new Response(JSON.stringify({
          article_id: articleId,
          guest_public: serverGuestPublic.get(articleId),
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      if (url.startsWith('/api/article/') && method === 'DELETE') {
        deleteRequests.push(url);
        if (shouldFailNextDelete) {
          shouldFailNextDelete = false;
          return new Response(
            JSON.stringify({ detail: 'Temporary delete failure' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } },
          );
        }
        deletedIds.add(url.split('/').pop() ?? '');
        return new Response(
          JSON.stringify({ message: 'deleted' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      return new Response('not found', { status: 404 });
    });
    return {
      mock,
      deleteRequests,
      guestPublicRequests,
      serverGuestPublic,
      releaseFirstGuestPublicFailure,
    };
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

  it('allows selecting multiple articles and deleting them together', async () => {
    setupFetchMocks();
    renderWithAuth();

    const user = userEvent.setup();

    await openTab(user, '文章インポート');

    await waitFor(() => expect(screen.getByText('インポート済み文章')).toBeInTheDocument());

    const checkbox1 = await screen.findByRole('checkbox', { name: '文章 First article を選択' });
    const checkbox2 = await screen.findByRole('checkbox', { name: '文章 Second article を選択' });

    await act(async () => {
      await user.click(checkbox1);
      await user.click(checkbox2);
    });

    const bulkButton = await screen.findByRole('button', { name: '選択した文章を削除' });
    expect(bulkButton).not.toBeDisabled();

    await act(async () => {
      await user.click(bulkButton);
    });

    expect(await screen.findByText(/実行後はこの画面から取り消せません/)).toBeInTheDocument();
    const confirmYes = await screen.findByRole('button', { name: '削除する' });
    await act(async () => {
      await user.click(confirmYes);
    });

    await waitFor(() => expect(screen.getByText('文章を2件削除しました')).toBeInTheDocument());

    await waitFor(() => {
      expect(screen.queryByText('First article')).not.toBeInTheDocument();
      expect(screen.queryByText('Second article')).not.toBeInTheDocument();
      expect(screen.getByText('Third article')).toBeInTheDocument();
    });
  });

  it('keeps the list and selection after a failed bulk delete so the user can retry', async () => {
    const { deleteRequests } = setupFetchMocks({ failFirstDelete: true });
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');
    await waitFor(() => expect(screen.getByText('インポート済み文章')).toBeInTheDocument());

    const checkbox1 = await screen.findByRole('checkbox', { name: '文章 First article を選択' });
    const checkbox2 = await screen.findByRole('checkbox', { name: '文章 Second article を選択' });
    await act(async () => {
      await user.click(checkbox1);
      await user.click(checkbox2);
    });

    await act(async () => {
      await user.click(await screen.findByRole('button', { name: '選択した文章を削除' }));
    });
    await act(async () => {
      await user.click(await screen.findByRole('button', { name: '削除する' }));
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('文章の削除に失敗しました:');
    expect(screen.getByText('First article')).toBeInTheDocument();
    expect(screen.getByText('Second article')).toBeInTheDocument();
    expect(screen.getByText('Third article')).toBeInTheDocument();
    expect(screen.getByText('選択中: 2件')).toBeInTheDocument();
    expect(checkbox1).toBeChecked();
    expect(checkbox2).toBeChecked();
    expect(screen.getByRole('button', { name: '選択した文章を削除' })).toBeEnabled();
    expect(deleteRequests).toEqual(['/api/article/article-1']);

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '選択した文章を削除' }));
    });
    await act(async () => {
      await user.click(await screen.findByRole('button', { name: '削除する' }));
    });

    await waitFor(() => expect(screen.getByText('文章を2件削除しました')).toBeInTheDocument());
    expect(deleteRequests).toEqual([
      '/api/article/article-1',
      '/api/article/article-1',
      '/api/article/article-2',
    ]);
    expect(screen.getByText('選択中: 0件')).toBeInTheDocument();
    expect(screen.queryByText('First article')).not.toBeInTheDocument();
    expect(screen.queryByText('Second article')).not.toBeInTheDocument();
    expect(screen.getByText('Third article')).toBeInTheDocument();
  });

  it('lets the owner review an article, recover from a public-toggle failure, and change it back to private', async () => {
    const {
      guestPublicRequests,
      serverGuestPublic,
      releaseFirstGuestPublicFailure,
    } = setupFetchMocks({ failFirstGuestPublic: true });
    renderWithAuth();

    const user = userEvent.setup();
    await openTab(user, '文章インポート');
    await waitFor(() => expect(screen.getByText('インポート済み文章')).toBeInTheDocument());

    await act(async () => {
      await user.click(screen.getByText('First article'));
    });
    const preview = await screen.findByRole('dialog', { name: '文章プレビュー' });
    expect(within(preview).getByRole('heading', { name: 'First article' })).toBeInTheDocument();
    expect(within(preview).getByText('Review this article before sharing.')).toBeInTheDocument();
    await act(async () => {
      await user.click(within(preview).getByRole('button', { name: '文章プレビューを閉じる' }));
    });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '文章プレビュー' })).not.toBeInTheDocument());

    const targetCard = () => within(screen.getByText('First article').closest('.al-card') as HTMLElement);
    const otherCard = () => within(screen.getByText('Second article').closest('.al-card') as HTMLElement);
    await act(async () => {
      await user.click(targetCard().getByRole('button', { name: '公開にする' }));
    });
    await waitFor(() => expect(guestPublicRequests).toHaveLength(1));

    expect(guestPublicRequests).toEqual([{ articleId: 'article-1', guestPublic: true }]);
    expect(serverGuestPublic.get('article-1')).toBe(false);
    expect(targetCard().getByText('公開中')).toBeInTheDocument();
    expect(targetCard().getByRole('button', { name: '非公開にする' })).toBeInTheDocument();
    expect(otherCard().getByText('非公開')).toBeInTheDocument();
    expect(otherCard().getByRole('button', { name: '公開にする' })).toBeInTheDocument();

    await act(async () => {
      releaseFirstGuestPublicFailure(new Response(
        JSON.stringify({ detail: 'Temporary public update failure' }),
        { status: 503, headers: { 'Content-Type': 'application/json' } },
      ));
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Temporary public update failure');
    expect(serverGuestPublic.get('article-1')).toBe(false);
    expect(targetCard().getByText('非公開')).toBeInTheDocument();
    expect(targetCard().getByRole('button', { name: '公開にする' })).toBeInTheDocument();
    expect(otherCard().getByText('非公開')).toBeInTheDocument();

    await act(async () => {
      await user.click(targetCard().getByRole('button', { name: '公開にする' }));
    });
    const publicNotice = await screen.findByText('Reader記事をゲスト公開しました');
    expect(publicNotice.closest('[role="status"]')).toBeInTheDocument();
    expect(guestPublicRequests).toEqual([
      { articleId: 'article-1', guestPublic: true },
      { articleId: 'article-1', guestPublic: true },
    ]);
    expect(serverGuestPublic.get('article-1')).toBe(true);
    expect(targetCard().getByText('公開中')).toBeInTheDocument();
    expect(targetCard().getByRole('button', { name: '非公開にする' })).toBeInTheDocument();
    expect(otherCard().getByText('非公開')).toBeInTheDocument();

    await act(async () => {
      await user.click(targetCard().getByRole('button', { name: '非公開にする' }));
    });
    const privateNotice = await screen.findByText('Reader記事を非公開にしました');
    expect(privateNotice.closest('[role="status"]')).toBeInTheDocument();
    expect(guestPublicRequests).toEqual([
      { articleId: 'article-1', guestPublic: true },
      { articleId: 'article-1', guestPublic: true },
      { articleId: 'article-1', guestPublic: false },
    ]);
    expect(serverGuestPublic.get('article-1')).toBe(false);
    expect(targetCard().getByText('非公開')).toBeInTheDocument();
    expect(targetCard().getByRole('button', { name: '公開にする' })).toBeInTheDocument();
    expect(otherCard().getByText('非公開')).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: '文章プレビュー' })).not.toBeInTheDocument();
  });
});
