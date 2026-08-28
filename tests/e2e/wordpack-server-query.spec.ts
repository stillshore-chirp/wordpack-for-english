import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

type Visibility = 'public' | 'private';

type WordPackListFixture = {
  id: string;
  lemma: string;
  sense_title: string;
  created_at: string;
  updated_at: string;
  is_empty: boolean;
  guest_public: boolean;
  examples_count: {
    Dev: number;
    CS: number;
    LLM: number;
    Business: number;
    Common: number;
  };
  checked_only_count: number;
  learned_count: number;
};

const makeWordPack = (
  id: string,
  lemma: string,
  { visibility = 'private' as Visibility, generated = true } = {},
): WordPackListFixture => ({
  id,
  lemma,
  sense_title: '全ページ検索の確認用WordPack',
  created_at: '2026-08-28T01:00:00Z',
  updated_at: '2026-08-28T02:00:00Z',
  is_empty: !generated,
  guest_public: visibility === 'public',
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
  { visibility: 'public' },
);

const prepareAuthenticatedPage = async (context: BrowserContext, page: Page) => {
  await seedAuthenticatedSession(context, page);
  await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });
};

const response = (
  items: WordPackListFixture[],
  {
    total = 201,
    filteredTotal,
    offset = 0,
    publicCount = 1,
    privateCount = 200,
    generatedCount = 201,
    notGeneratedCount = 0,
  }: {
    total?: number;
    filteredTotal: number;
    offset?: number;
    publicCount?: number;
    privateCount?: number;
    generatedCount?: number;
    notGeneratedCount?: number;
  },
) => json({
  items,
  total,
  filtered_total: filteredTotal,
  facet_counts: {
    public: publicCount,
    private: privateCount,
    generated: generatedCount,
    not_generated: notGeneratedCount,
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
    await page.setViewportSize({ width: 390, height: 844 });
    const requestedQueries: URLSearchParams[] = [];

    await page.route('**/api/word/packs?**', (route: Route) => {
      const url = new URL(route.request().url());
      requestedQueries.push(new URLSearchParams(url.searchParams));
      if (url.searchParams.get('visibility') === 'public') {
        return route.fulfill(
          response([laterPublic], {
            filteredTotal: 1,
            publicCount: 1,
            privateCount: 200,
            generatedCount: 1,
            notGeneratedCount: 0,
          }),
        );
      }
      return route.fulfill(response(firstPage, { filteredTotal: 201 }));
    });

    await page.goto('/');
    await expect(page.getByText('全体 201件')).toBeVisible();
    await expect(page.getByRole('button', { name: '公開中 1' })).toBeVisible();
    await expect(page.getByRole('button', { name: '非公開 200' })).toBeVisible();
    await expect(page.getByRole('button', { name: '生成済み 201' })).toBeVisible();

    await page.getByRole('button', { name: '公開中 1' }).click();

    await expect(page.getByRole('heading', { name: 'later-page-only' })).toBeVisible();
    await expect(page.getByText('全体 201件')).toBeVisible();
    await expect(page.getByText('条件一致（全ページ） 1件')).toBeVisible();
    await expect(page.getByText('このページ 1件')).toBeVisible();
    await expect(page.getByText('検索・絞り込み条件に一致するWordPackがありません。')).toHaveCount(0);
    expect(
      requestedQueries.some(
        (params) => (
          params.get('visibility') === 'public'
          && params.get('offset') === '0'
          && params.get('sort_key') === 'updated_at'
          && params.get('sort_order') === 'desc'
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
    expect(layout.filterButtonHeights.length).toBeGreaterThan(0);
    for (const height of layout.filterButtonHeights) {
      expect(height).toBeGreaterThanOrEqual(44);
    }
    await runA11yCheck(page);
  });

  test('2ページ目から条件を変えるとoffset=0で再検索し、全ページ件数とfacet件数を更新する', async ({
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
            generatedCount: 0,
            notGeneratedCount: 0,
          }),
        );
      }
      if (search === 'later-page-only') {
        return route.fulfill(
          response([laterPublic], {
            filteredTotal: 1,
            publicCount: 1,
            privateCount: 0,
            generatedCount: 1,
            notGeneratedCount: 0,
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
    await expect(page.getByRole('button', { name: '次へ' })).toBeVisible();
    await page.getByRole('button', { name: '次へ' }).click();
    await expect(page.getByText('201-201 / 201件')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'later-page-only' })).toBeVisible();

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
    await expect(page.getByText('条件一致（全ページ） 1件')).toBeVisible();
    await expect(page.getByText('全体 201件')).toBeVisible();
    await expect(page.getByText('このページ 1件')).toBeVisible();
    await expect(page.getByRole('button', { name: '公開中 1' })).toBeVisible();
    await expect(page.getByRole('button', { name: '非公開 0' })).toBeVisible();
    await expect(page.getByRole('button', { name: '生成済み 1' })).toBeVisible();
    await runA11yCheck(page);

    await searchInput.fill('missing');
    await searchInput.press('Enter');
    await expect(page.getByText('検索・絞り込み条件に一致するWordPackがありません。')).toBeVisible();
    await expect(page.getByText('条件一致（全ページ） 0件')).toBeVisible();
    await expect(page.getByText('このページ 0件')).toBeVisible();
    await expect(page.getByText('保存済みのWordPackがありません。')).toHaveCount(0);
    await expect(page.getByTestId('wp-card')).toHaveCount(0);
    expect(
      requestedUrls.some(
        (url) => (
          url.searchParams.get('search') === 'missing'
          && url.searchParams.get('offset') === '0'
        ),
      ),
    ).toBe(true);
    await runA11yCheck(page);
  });

  test('条件取得に失敗したときは前回の一覧を保持し、再試行後に新条件へ切り替える', async ({
    context,
    page,
  }) => {
    await prepareAuthenticatedPage(context, page);
    let failedQueryAttempts = 0;
    const requestedUrls: URL[] = [];

    await page.route('**/api/word/packs?**', (route: Route) => {
      const url = new URL(route.request().url());
      requestedUrls.push(url);
      if (url.searchParams.get('search') === 'no-match') {
        failedQueryAttempts += 1;
        if (failedQueryAttempts === 1) {
          return route.fulfill(
            json({ detail: '検索条件を一時的に適用できません。' }, 503),
          );
        }
        return route.fulfill(
          response([], {
            filteredTotal: 0,
            publicCount: 0,
            privateCount: 0,
            generatedCount: 0,
            notGeneratedCount: 0,
          }),
        );
      }
      return route.fulfill(response(firstPage, { filteredTotal: 201 }));
    });

    await page.goto('/');
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    const searchInput = page.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await searchInput.fill('no-match');
    await searchInput.press('Enter');

    await expect(page.getByRole('alert')).toContainText('検索・絞り込み条件を適用できませんでした');
    await expect(page.getByRole('alert')).toContainText('前回の一覧を表示しています');
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    await expect(page.getByRole('heading', { name: 'private-first-001' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'private-first-002' })).toBeVisible();
    await expect(page.getByText('条件一致（全ページ） —')).toBeVisible();
    await expect(page.getByText('このページ 前回の表示')).toBeVisible();
    await expect(page.getByRole('button', { name: '再試行' })).toBeVisible();
    expect(requestedUrls.at(-1)?.searchParams.get('offset')).toBe('0');
    expect(failedQueryAttempts).toBe(1);
    await runA11yCheck(page);

    await page.getByRole('button', { name: '再試行' }).click();
    await expect(page.getByText('検索・絞り込み条件に一致するWordPackがありません。')).toBeVisible();
    await expect(page.getByTestId('wp-card')).toHaveCount(0);
    expect(failedQueryAttempts).toBe(2);
    await runA11yCheck(page);
  });
});
