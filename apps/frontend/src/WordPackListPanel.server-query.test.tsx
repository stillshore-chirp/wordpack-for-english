import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

type ListResponse = {
  items: Array<Record<string, unknown>>;
  total: number;
  filtered_total: number;
  facet_counts: {
    public: number;
    private: number;
    generated: number;
    not_generated: number;
  };
  limit: number;
  offset: number;
};

const makeItem = (id: string, lemma: string, guestPublic = true) => ({
  id,
  lemma,
  sense_title: `${lemma} overview`,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: '2026-08-02T00:00:00Z',
  is_empty: false,
  examples_count: { Dev: 1, CS: 0, LLM: 0, Business: 0, Common: 0 },
  checked_only_count: 0,
  learned_count: 0,
  guest_public: guestPublic,
});

const makeResponse = (
  items: Array<Record<string, unknown>>,
  total: number,
  filteredTotal: number,
  offset: number,
  facetCounts = { public: 1, private: 0, generated: 1, not_generated: 0 },
  status = 200,
) => new Response(
  JSON.stringify({
    items,
    total,
    filtered_total: filteredTotal,
    facet_counts: facetCounts,
    limit: 200,
    offset,
  } satisfies ListResponse),
  { status, headers: { 'Content-Type': 'application/json' } },
);

const renderWithAuth = () => render(
  <AppProviders googleClientId="test-client">
    <App />
  </AppProviders>,
);

describe('WordPackListPanel server-side query', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try {
      sessionStorage.clear();
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
    } catch {
      // storage が利用できない環境でもAPIクエリの観測は継続する。
    }
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {
      // ignore
    }
  });

  it('サーバー側の条件・並び順を送り、範囲外ページを最後の有効ページへ補正する', async () => {
    const requests: URL[] = [];
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
        const parsed = new URL(url, 'http://localhost');
        requests.push(parsed);
        const offset = Number(parsed.searchParams.get('offset'));
        if (offset === 200) {
          // 件数が変動して空になった場合、クライアントはoffset=0へ再取得する。
          return makeResponse([], 201, 1, offset);
        }
        if (requests.some((request) => request.searchParams.get('offset') === '200')) {
          return makeResponse([makeItem('wp:alpha', 'alpha')], 201, 1, offset);
        }
        return makeResponse(
          [makeItem('wp:alpha', 'alpha')],
          201,
          201,
          offset,
          { public: 1, private: 200, generated: 1, not_generated: 200 },
        );
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderWithAuth();

    await waitFor(() => expect(screen.getByRole('button', { name: '次へ' })).toBeInTheDocument());
    const initialRequest = requests[0];
    expect(initialRequest.searchParams.get('limit')).toBe('200');
    expect(initialRequest.searchParams.get('offset')).toBe('0');
    expect(initialRequest.searchParams.get('search_mode')).toBe('contains');
    expect(initialRequest.searchParams.get('visibility')).toBe('all');
    expect(initialRequest.searchParams.get('generation')).toBe('all');
    expect(initialRequest.searchParams.get('sort_key')).toBe('updated_at');
    expect(initialRequest.searchParams.get('sort_order')).toBe('desc');

    await userEvent.setup().click(screen.getByRole('button', { name: '次へ' }));

    await waitFor(() => expect(
      requests.filter((request) => request.searchParams.get('offset') === '200'),
    ).toHaveLength(1));
    await waitFor(() => expect(
      requests.filter((request) => request.searchParams.get('offset') === '0'),
    ).toHaveLength(2));
    expect(screen.getByText('条件一致（全ページ） 1件')).toBeInTheDocument();
    expect(screen.getByText('このページ 1件')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '非公開 0' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '次へ' })).not.toBeInTheDocument();

    expect(fetchMock).toHaveBeenCalled();
  });

  it('ページ移動後の条件変更はoffset=0で再取得し、全体件数とfacet件数を表示する', async () => {
    const requests: URL[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';
      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        const parsed = new URL(url, 'http://localhost');
        requests.push(parsed);
        const offset = Number(parsed.searchParams.get('offset'));
        if (parsed.searchParams.get('search') === 'alp') {
          return makeResponse(
            [makeItem('wp:alpha', 'alpha')],
            401,
            1,
            offset,
            { public: 1, private: 0, generated: 1, not_generated: 0 },
          );
        }
        if (parsed.searchParams.get('visibility') === 'public') {
          return makeResponse(
            [makeItem('wp:alpha', 'alpha')],
            401,
            1,
            offset,
            { public: 1, private: 0, generated: 1, not_generated: 0 },
          );
        }
        if (offset === 200) return makeResponse([makeItem('wp:beta', 'beta')], 401, 401, offset, { public: 1, private: 400, generated: 1, not_generated: 400 });
        return makeResponse([makeItem('wp:alpha', 'alpha')], 401, 401, offset, { public: 1, private: 400, generated: 1, not_generated: 400 });
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderWithAuth();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '次へ' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '次へ' }));
    await waitFor(() => expect(screen.getAllByTestId('wp-card')[0]).toHaveTextContent('beta'));

    const topSearch = screen.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await user.type(topSearch, 'alp');
    await user.keyboard('{Enter}');
    await waitFor(() => expect(
      requests.some((request) => (
        request.searchParams.get('offset') === '0'
        && request.searchParams.get('search') === 'alp'
        && request.searchParams.get('search_mode') === 'contains'
      )),
    ).toBe(true));

    await user.click(screen.getByRole('button', { name: '公開中 1' }));
    await waitFor(() => expect(
      requests.some((request) => (
        request.searchParams.get('offset') === '0'
        && request.searchParams.get('visibility') === 'public'
      )),
    ).toBe(true));
    await waitFor(() => expect(screen.getByText('条件一致（全ページ） 1件')).toBeInTheDocument());
    expect(screen.getByText('全体 401件')).toBeInTheDocument();
    expect(screen.getByText('このページ 1件')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '非公開 0' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '生成済み 1' }));
    await waitFor(() => expect(
      requests.some((request) => (
        request.searchParams.get('offset') === '0'
        && request.searchParams.get('generation') === 'generated'
      )),
    ).toBe(true));

    await user.selectOptions(screen.getByLabelText('並び順:'), 'lemma');
    await waitFor(() => expect(
      requests.some((request) => (
        request.searchParams.get('offset') === '0'
        && request.searchParams.get('sort_key') === 'lemma'
      )),
    ).toBe(true));
  });

  it('条件取得に失敗したときは前回の一覧を保持し、条件一致数を未取得として示す', async () => {
    const requests: URL[] = [];
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';
      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        const parsed = new URL(url, 'http://localhost');
        requests.push(parsed);
        if (parsed.searchParams.get('visibility') === 'public') {
          return new Response(JSON.stringify({ detail: '条件取得に失敗しました' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return makeResponse([makeItem('wp:alpha', 'alpha')], 3, 3, 0, { public: 1, private: 2, generated: 1, not_generated: 2 });
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderWithAuth();
    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: '公開中 1' })).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '公開中 1' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('検索・絞り込み条件を適用できませんでした'));
    expect(requests.at(-1)?.searchParams.get('offset')).toBe('0');
    expect(screen.getByTestId('wp-card')).toHaveTextContent('alpha');
    expect(screen.getByText('条件一致（全ページ） —')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument();
  });

  it('前回の条件一致が0件でも、新条件の取得失敗を保存済み0件と誤表示しない', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';
      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(JSON.stringify({ request_timeout_ms: 60000 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        });
      }
      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        const parsed = new URL(url, 'http://localhost');
        if (parsed.searchParams.get('visibility') === 'public') {
          return new Response(JSON.stringify({ detail: '条件取得に失敗しました' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          });
        }
        return makeResponse(
          [],
          3,
          0,
          0,
          { public: 1, private: 2, generated: 1, not_generated: 2 },
        );
      }
      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });

    renderWithAuth();
    const user = userEvent.setup();
    await waitFor(() => expect(
      screen.getByText('検索・絞り込み条件に一致するWordPackがありません。'),
    ).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: '公開中 1' }));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
      '検索・絞り込み条件を適用できませんでした',
    ));
    expect(screen.getByText('検索・絞り込み条件に一致するWordPackがありません。')).toBeInTheDocument();
    expect(screen.queryByText('保存済みのWordPackがありません。')).not.toBeInTheDocument();
    expect(screen.getByText(
      '前回成功した条件では0件でした。条件を変更するか、上の再試行を実行してください。',
    )).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '再試行' })).toBeInTheDocument();
  });
});
