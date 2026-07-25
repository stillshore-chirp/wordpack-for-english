import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NotificationsProvider } from '../../NotificationsContext';
import type { WordPackListItem } from '../../features/wordpack/types';
import { ShelvesPage } from './index';

vi.mock('../../SettingsContext', () => ({
  useSettings: () => ({
    settings: {
      apiBase: '/api',
      requestTimeoutMs: 60000,
    },
  }),
  useOptionalSettings: () => ({
    settings: {
      apiBase: '/api',
      requestTimeoutMs: 60000,
    },
  }),
}));

const wordPacks: WordPackListItem[] = [
  {
    id: 'wp:robust',
    lemma: 'robust',
    sense_title: '壊れにくい',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-03T00:00:00Z',
    is_empty: false,
    guest_public: true,
    examples_count: { Dev: 3, CS: 0, LLM: 0, Business: 2, Common: 1 },
    checked_only_count: 2,
    learned_count: 1,
  },
  {
    id: 'wp:stale',
    lemma: 'stale',
    sense_title: '',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-02T00:00:00Z',
    is_empty: true,
    guest_public: false,
    examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
    checked_only_count: 0,
    learned_count: 0,
  },
];

interface ListPayload {
  items: WordPackListItem[];
  total: number;
}

type ListResponseFactory = (
  offset: number,
  requestIndex: number,
) => Response | Promise<Response>;

const jsonResponse = (payload: unknown, status = 200): Response =>
  new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const setupFetch = (
  factory: ListResponseFactory = () =>
    jsonResponse({
      items: wordPacks,
      total: wordPacks.length,
      limit: 200,
      offset: 0,
    }),
) => {
  let requestIndex = 0;
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.startsWith('/api/word/packs?')) {
      const parsed = new URL(url, 'http://localhost');
      const offset = Number(parsed.searchParams.get('offset') ?? 0);
      const response = factory(offset, requestIndex);
      requestIndex += 1;
      return Promise.resolve(response);
    }
    return Promise.resolve(jsonResponse({}));
  });
  globalThis.fetch = fetchMock as typeof fetch;
  return fetchMock;
};

const renderPage = async () => {
  let result: ReturnType<typeof render> | undefined;
  await act(async () => {
    result = render(
      <NotificationsProvider persist={false}>
        <ShelvesPage />
      </NotificationsProvider>,
    );
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  });
  return result;
};

describe('ShelvesPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('moves focus to the selected shelf results and supports reopening the active shelf', async () => {
    setupFetch();
    await renderPage();

    const user = userEvent.setup();
    const currentShelfButton = await screen.findByRole('button', {
      name: '「最近更新」棚のWordPack一覧へ移動',
    });
    await act(async () => {
      await user.click(currentShelfButton);
    });

    const recentResults = screen.getByRole('region', { name: '最近更新' });
    const recentHeading = within(recentResults).getByRole('heading', {
      name: '最近更新',
      level: 3,
    });
    await waitFor(() => expect(recentHeading).toHaveFocus());
    expect(recentHeading.scrollIntoView).toHaveBeenCalledWith({
      behavior: 'smooth',
      block: 'start',
    });
    expect(
      within(recentResults).getByRole('status', { name: '' }),
    ).toHaveTextContent('最近更新のWordPackを2件表示しました。');

    const search = screen.getByRole('searchbox', {
      name: '棚とWordPackを検索',
    });
    await act(async () => {
      await user.click(search);
      await user.type(search, 'rob');
    });
    expect(search).toHaveFocus();
    expect(search).toHaveValue('rob');
    await act(async () => {
      await user.clear(search);
    });

    await act(async () => {
      await user.click(
        screen.getByRole('button', {
          name: '「未生成」棚のWordPack一覧を表示',
        }),
      );
    });
    const emptyResults = await screen.findByRole('region', { name: '未生成' });
    await waitFor(() =>
      expect(
        within(emptyResults).getByRole('heading', {
          name: '未生成',
          level: 3,
        }),
      ).toHaveFocus(),
    );
    expect(within(emptyResults).getByRole('heading', { name: 'stale' })).toBeInTheDocument();
    expect(localStorage.getItem('wp.localShelves.v1')).toBeNull();
  });

  it('keeps shelf matches, item counts, active results, and no-results recovery consistent', async () => {
    setupFetch();
    await renderPage();
    const user = userEvent.setup();
    const search = await screen.findByRole('searchbox', {
      name: '棚とWordPackを検索',
    });

    await act(async () => {
      await user.type(search, '未生成');
    });
    const emptyShelf = await screen.findByRole('button', {
      name: '「未生成」棚のWordPack一覧へ移動',
    });
    expect(emptyShelf).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('region', { name: '未生成' })).toHaveTextContent('stale');
    expect(screen.queryByText('この棚に入るWordPackはまだありません。')).not.toBeInTheDocument();

    await act(async () => {
      await user.clear(search);
      await user.type(search, '一致しない検索語');
    });
    expect(
      await screen.findByText('「一致しない検索語」に一致する棚やWordPackはありません。'),
    ).toBeInTheDocument();
    expect(screen.getByText('保存済み2件')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: '未生成' })).not.toBeInTheDocument();
    expect(screen.queryByText('この棚に入るWordPackはまだありません。')).not.toBeInTheDocument();

    await act(async () => {
      await user.click(screen.getByRole('button', { name: '検索を解除' }));
    });
    expect(search).toHaveFocus();
    expect(await screen.findByRole('region', { name: '未生成' })).toBeInTheDocument();
  });

  it('provides unique action names, Japanese copy, and a working search shortcut', async () => {
    setupFetch();
    await renderPage();

    expect(
      await screen.findByRole('button', {
        name: '「未生成」棚のWordPack一覧を表示',
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'robustをプレビュー' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'staleをプレビュー' })).toBeInTheDocument();
    expect(screen.queryByText(/entries|shown|guest_public/)).not.toBeInTheDocument();
    expect(screen.getByText('⌘/Ctrl K')).toBeInTheDocument();

    const search = screen.getByRole('searchbox', {
      name: '棚とWordPackを検索',
    });
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    document.body.append(dialog);
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(search).not.toHaveFocus();
    dialog.remove();

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(search).toHaveFocus();
  });

  it('separates the initial loading state from the first empty state', async () => {
    let resolveList: ((response: Response) => void) | undefined;
    setupFetch(
      () =>
        new Promise<Response>((resolve) => {
          resolveList = resolve;
        }),
    );
    await renderPage();

    expect(
      screen.getByText('保存済みWordPackを読み込んでいます…'),
    ).toHaveAttribute('role', 'status');
    expect(screen.getByText('読み込み中')).toBeInTheDocument();
    expect(screen.queryByText('最近更新', { selector: '.dictionary-badge' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('棚の集計')).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '自動分類の棚一覧' })).not.toBeInTheDocument();

    await act(async () => {
      resolveList?.(
        jsonResponse({
          items: [],
          total: 0,
          limit: 200,
          offset: 0,
        }),
      );
    });

    expect(await screen.findByText('保存済みWordPackはまだありません。')).toBeInTheDocument();
    expect(screen.getByText('保存なし')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Lexiconを開く' })).toHaveAttribute(
      'href',
      '/lexicon',
    );
    expect(screen.queryByRole('list', { name: '自動分類の棚一覧' })).not.toBeInTheDocument();
  });

  it('shows an initial error with a retry that can recover', async () => {
    setupFetch((_offset, requestIndex) =>
      requestIndex === 0
        ? jsonResponse({ detail: '一時的に取得できません' }, 503)
        : jsonResponse({
          items: wordPacks,
          total: wordPacks.length,
          limit: 200,
          offset: 0,
        }),
    );
    await renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('棚を表示できません');
    expect(screen.getByText('取得失敗')).toBeInTheDocument();
    expect(screen.queryByLabelText('棚の集計')).not.toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '自動分類の棚一覧' })).not.toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: '一覧を再読み込み' }));
    });
    expect(await screen.findByRole('list', { name: '自動分類の棚一覧' })).toBeInTheDocument();
  });

  it('keeps the last successful list visible when a refresh fails', async () => {
    setupFetch((_offset, requestIndex) =>
      requestIndex === 0
        ? jsonResponse({
          items: wordPacks,
          total: wordPacks.length,
          limit: 200,
          offset: 0,
        })
        : jsonResponse({ detail: '更新に失敗しました' }, 503),
    );
    await renderPage();
    const user = userEvent.setup();

    expect(await screen.findByRole('heading', { name: 'robust' })).toBeInTheDocument();
    await act(async () => {
      await user.click(screen.getByRole('button', { name: '更新' }));
    });

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('前回取得した2件を表示しています');
    expect(screen.getByRole('heading', { name: 'robust' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'もう一度更新' })).toBeInTheDocument();
  });

  it('loads every API page before classifying shelves', async () => {
    const allItems = Array.from({ length: 201 }, (_, index): WordPackListItem => ({
      ...wordPacks[0],
      id: `wp:all:${index}`,
      lemma: `lemma-${index}`,
      guest_public: true,
    }));
    const fetchMock = setupFetch((offset) => {
      const items = allItems.slice(offset, offset + 200);
      const payload: ListPayload & { limit: number; offset: number } = {
        items,
        total: allItems.length,
        limit: 200,
        offset,
      };
      return jsonResponse(payload);
    });
    await renderPage();

    expect(
      await screen.findByRole('button', {
        name: '「ゲスト公開中」棚のWordPack一覧を表示',
      }),
    ).toBeInTheDocument();
    const guestShelf = screen
      .getByRole('heading', { name: 'ゲスト公開中', level: 4 })
      .closest('article');
    expect(guestShelf).toHaveTextContent('201件');
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('limit=200&offset=200'),
      expect.anything(),
    );
  });

  it('reports partial data when the API cannot return the remaining page', async () => {
    const firstPage = Array.from({ length: 200 }, (_, index): WordPackListItem => ({
      ...wordPacks[0],
      id: `wp:partial:${index}`,
      lemma: `partial-${index}`,
    }));
    setupFetch((offset) =>
      jsonResponse({
        items: offset === 0 ? firstPage : [],
        total: 201,
        limit: 200,
        offset,
      }),
    );
    await renderPage();

    expect(
      await screen.findByText(
        '全201件のうち200件を取得しました。表示中の件数だけで棚を分類しています。',
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '全件を再読み込み' })).toBeInTheDocument();
  });

  it('keeps completed pages visible when a later page fails', async () => {
    const firstPage = Array.from({ length: 200 }, (_, index): WordPackListItem => ({
      ...wordPacks[0],
      id: `wp:page-error:${index}`,
      lemma: `page-error-${index}`,
    }));
    setupFetch((offset) =>
      offset === 0
        ? jsonResponse({
          items: firstPage,
          total: 201,
          limit: 200,
          offset,
        })
        : jsonResponse({ detail: '続きを取得できません' }, 503),
    );
    await renderPage();

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(
      '続きを取得できません。全201件のうち200件を取得し、表示中の件数だけで棚を分類しています。',
    );
    expect(screen.getByRole('heading', { name: 'page-error-0' })).toBeInTheDocument();
    expect(screen.getByLabelText('棚の集計')).toHaveTextContent('201保存済み');
    expect(screen.getByRole('button', { name: '全件を再読み込み' })).toBeInTheDocument();
    expect(screen.queryByText(/棚を表示できません/)).not.toBeInTheDocument();
  });
});
