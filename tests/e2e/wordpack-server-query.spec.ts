import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const makeWordPack = (
  id: string,
  lemma: string,
  { public: guestPublic = false, generated = true } = {},
) => ({
  id,
  lemma,
  sense_title: '全ページ検索の確認用WordPack',
  created_at: '2026-07-24T01:00:00Z',
  updated_at: '2026-07-24T02:00:00Z',
  is_empty: !generated,
  guest_public: guestPublic,
  examples_count: {
    Dev: generated ? 1 : 0,
    CS: 0,
    LLM: 0,
    Business: 0,
    Common: 0,
  },
  checked_only_count: 0,
  learned_count: 0,
});

const firstPage = [
  makeWordPack('wp:e2e:first-001', 'private-first-001'),
  makeWordPack('wp:e2e:first-002', 'private-first-002'),
];
const laterPublic = makeWordPack(
  'wp:e2e:later-public',
  'later-page-only',
  { public: true },
);

const prepareAuthenticatedPage = async (context: BrowserContext, page: Page) => {
  await seedAuthenticatedSession(context, page);
  await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });
};

const response = (
  items: ReturnType<typeof makeWordPack>[],
  {
    filteredTotal,
    offset = 0,
    publicCount = 1,
    privateCount = 200,
  }: {
    filteredTotal: number;
    offset?: number;
    publicCount?: number;
    privateCount?: number;
  },
) => json({
  items,
  total: 201,
  filtered_total: filteredTotal,
  facet_counts: {
    public: publicCount,
    private: privateCount,
    generated: filteredTotal,
    not_generated: 0,
  },
  limit: 200,
  offset,
});

test.describe('Lexicon WordPack一覧の全ページ検索・ページング', () => {
  test('201件目だけにある公開WordPackを先頭ページの絞り込みから取得できる', async ({
    context,
    page,
  }) => {
    await prepareAuthenticatedPage(context, page);
    const requestedQueries: URLSearchParams[] = [];
    await page.route('**/api/word/packs?**', (route: Route) => {
      const url = new URL(route.request().url());
      requestedQueries.push(url.searchParams);
      if (url.searchParams.get('visibility') === 'public') {
        return route.fulfill(
          response([laterPublic], {
            filteredTotal: 1,
            publicCount: 1,
            privateCount: 200,
          }),
        );
      }
      return route.fulfill(response(firstPage, { filteredTotal: 201 }));
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');

    await expect(page.getByLabel('全体件数 201件')).toBeVisible();
    await page.getByRole('button', { name: '公開中 1' }).click();

    await expect(page.getByRole('heading', { name: 'later-page-only' })).toBeVisible();
    await expect(page.getByText('条件一致（全ページ） 1件')).toBeVisible();
    await expect(page.getByRole('heading', { name: /一致するWordPackがありません/ })).toHaveCount(0);
    expect(
      requestedQueries.some(
        (params) => (
          params.get('visibility') === 'public'
          && params.get('offset') === '0'
          && params.get('sort_key') === 'updated_at'
        ),
      ),
    ).toBe(true);

    const layout = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      filterButtonHeights: Array.from(
        document.querySelectorAll<HTMLElement>('.wp-filter-chip-row button'),
      ).map((button) => button.getBoundingClientRect().height),
    }));
    expect(layout.scrollWidth).toBeLessThanOrEqual(layout.clientWidth + 1);
    for (const height of layout.filterButtonHeights) {
      expect(height).toBeGreaterThanOrEqual(44);
    }
    await runA11yCheck(page);
  });

  test('ページ移動後に条件を変えると0件目から再検索し、全ページ0件を区別する', async ({
    context,
    page,
  }) => {
    await prepareAuthenticatedPage(context, page);
    const requestedUrls: URL[] = [];
    await page.route('**/api/word/packs?**', (route: Route) => {
      const url = new URL(route.request().url());
      requestedUrls.push(url);
      const search = url.searchParams.get('search') ?? '';
      const offset = Number(url.searchParams.get('offset') ?? '0');
      if (search === 'missing') {
        return route.fulfill(
          response([], {
            filteredTotal: 0,
            publicCount: 0,
            privateCount: 0,
          }),
        );
      }
      if (search === 'later-page-only') {
        return route.fulfill(
          response([laterPublic], {
            filteredTotal: 1,
            publicCount: 1,
            privateCount: 0,
          }),
        );
      }
      if (offset === 200) {
        return route.fulfill(
          response([laterPublic], {
            filteredTotal: 201,
            offset: 200,
          }),
        );
      }
      return route.fulfill(response(firstPage, { filteredTotal: 201 }));
    });
    await page.goto('/');

    await page.getByRole('button', { name: '次へ' }).click();
    await expect(page.getByText('201-201 / 201件')).toBeVisible();

    const searchInput = page.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await searchInput.fill('later-page-only');
    await searchInput.press('Enter');
    await expect(page.getByRole('heading', { name: 'later-page-only' })).toBeVisible();
    expect(
      requestedUrls.some(
        (url) => (
          url.searchParams.get('search') === 'later-page-only'
          && url.searchParams.get('search_mode') === 'contains'
          && url.searchParams.get('offset') === '0'
        ),
      ),
    ).toBe(true);

    await searchInput.fill('missing');
    await searchInput.press('Enter');
    await expect(page.getByRole('heading', { name: '検索条件に一致するWordPackがありません' })).toBeVisible();
    await expect(page.getByText(/全ページを確認しましたが/)).toBeVisible();
    await expect(page.getByRole('heading', { name: '保存済みWordPackはまだありません' })).toHaveCount(0);
    await expect(page.getByText('条件一致（全ページ） 0件')).toBeVisible();
    await runA11yCheck(page);
  });
});
