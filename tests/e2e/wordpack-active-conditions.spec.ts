import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const wordPacks = [
  {
    id: 'wp:e2e:condition-alpha',
    lemma: 'alpha',
    sense_title: '条件表示の確認用WordPack',
    created_at: '2024-01-10T09:15:00Z',
    updated_at: '2024-01-12T12:00:00Z',
    is_empty: false,
    guest_public: false,
    examples_count: { Dev: 2, CS: 0, LLM: 0, Business: 0, Common: 1 },
    checked_only_count: 1,
    learned_count: 2,
  },
  {
    id: 'wp:e2e:condition-bravo',
    lemma: 'bravo',
    sense_title: '条件表示の確認用WordPack',
    created_at: '2024-01-08T08:30:00Z',
    updated_at: '2024-01-11T18:05:00Z',
    is_empty: true,
    guest_public: true,
    examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
    checked_only_count: 0,
    learned_count: 0,
  },
];

const prepareAuthenticatedPage = async (context: BrowserContext, page: Page) => {
  await seedAuthenticatedSession(context, page);
  await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });
};

const fulfillWordPacks = (route: Route) => route.fulfill(
  json({
    items: wordPacks,
    total: wordPacks.length,
    limit: 200,
    offset: 0,
  }),
);

test.describe('Lexicon WordPack一覧の適用中条件', () => {
  test('複数条件を一覧領域で確認し個別または一括で解除できる', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    await page.route('**/api/word/packs?**', fulfillWordPacks);
    await page.goto('/');
    await expect(page.getByTestId('wp-card')).toHaveCount(2);

    const searchInput = page.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await searchInput.fill('alpha');
    await searchInput.press('Enter');
    await page.getByRole('button', { name: '非公開 1' }).click();
    await page.getByRole('button', { name: '生成済み 1' }).click();

    const conditionsHeading = page.getByRole('heading', { name: '適用中の条件' });
    const conditions = page.getByRole('list', { name: '適用中の検索・絞り込み条件' });
    await expect(conditionsHeading).toBeVisible();
    await expect(conditions).toContainText('検索: alpha（部分一致）');
    await expect(conditions).toContainText('公開状態: 非公開');
    await expect(conditions).toContainText('生成状態: 生成済み');
    await expect(page.getByLabel('全体件数 2件')).toHaveText('全体 2件');
    await expect(page.getByText('このページ 2件')).toBeVisible();
    await expect(page.getByText('条件一致 1件')).toBeVisible();
    await runA11yCheck(page);

    await page.getByRole('button', { name: '検索: alpha（部分一致）を解除' }).click();
    await expect(searchInput).toHaveValue('');
    await expect(conditionsHeading).toBeFocused();
    await expect(conditions).not.toContainText('検索: alpha（部分一致）');
    await expect(conditions).toContainText('公開状態: 非公開');

    await page.getByRole('button', { name: '公開状態: 非公開を解除' }).click();
    await expect(conditionsHeading).toBeFocused();
    await expect(conditions).toContainText('生成状態: 生成済み');

    await page.getByRole('button', { name: 'すべて解除' }).click();
    await expect(conditionsHeading).toHaveCount(0);
    await expect(page.getByRole('heading', { name: /保存済みWordPack/ })).toBeFocused();
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
  });

  test('狭幅でもセッション復元条件と解除操作を表示する', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    await page.addInitScript(() => {
      window.sessionStorage.setItem(
        'wp.list.ui_state.v1',
        JSON.stringify({
          sortKey: 'updated_at',
          sortOrder: 'desc',
          viewMode: 'card',
          generationFilter: 'generated',
          visibilityFilter: 'private',
          searchMode: 'prefix',
          searchInput: 'alp',
          appliedSearch: { mode: 'prefix', value: 'alp' },
          offset: 0,
          showAllSense: false,
        }),
      );
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/api/word/packs?**', fulfillWordPacks);
    await page.goto('/');

    const conditions = page.getByRole('list', { name: '適用中の検索・絞り込み条件' });
    await expect(conditions).toContainText('検索: alp（前方一致）');
    await expect(conditions).toContainText('公開状態: 非公開');
    await expect(conditions).toContainText('生成状態: 生成済み');
    await expect(page.getByRole('searchbox', { name: '保存済みWordPackを検索' })).toHaveValue('alp');
    await expect(page.getByTestId('wp-card')).toHaveCount(1);

    const layout = await page.evaluate(() => {
      const clearButtons = Array.from(
        document.querySelectorAll<HTMLElement>('.wp-active-conditions li button'),
      );
      return {
        documentClientWidth: document.documentElement.clientWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        clearButtonHeights: clearButtons.map((button) => button.getBoundingClientRect().height),
      };
    });
    expect(layout.documentScrollWidth).toBeLessThanOrEqual(layout.documentClientWidth + 1);
    expect(layout.clearButtonHeights).toHaveLength(3);
    for (const height of layout.clearButtonHeights) {
      expect(height).toBeGreaterThanOrEqual(44);
    }
    await runA11yCheck(page);
  });
});
