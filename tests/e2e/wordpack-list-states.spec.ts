import { expect, test, type BrowserContext, type Page, type Route } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const wordPacks = [
  {
    id: 'wp:e2e:state-alpha',
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
    id: 'wp:e2e:state-bravo',
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

const prepareAuthenticatedPage = async (context: BrowserContext, page: Page) => {
  await seedAuthenticatedSession(context, page);
  await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });
};

const fulfillWordPacks = (
  route: Route,
  items = wordPacks,
) => route.fulfill(
  json({
    items,
    total: items.length,
    limit: 200,
    offset: 0,
  }),
);

test.describe('Lexicon WordPack一覧の状態と回復導線', () => {
  test('初回空状態から新規作成へ進める', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    await page.route('**/api/word/packs?**', (route) => fulfillWordPacks(route, []));
    await page.goto('/');

    await expect(page.getByRole('heading', { name: '保存済みWordPackはまだありません' })).toBeVisible();
    await expect(page.getByRole('button', { name: '新しいWordPackを作成' })).toBeVisible();
    await runA11yCheck(page);

    await page.getByRole('button', { name: '新しいWordPackを作成' }).click();
    await expect(page.getByRole('textbox', { name: '見出し語' })).toBeFocused();
  });

  test('検索結果0件に条件と解除操作を示す', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    await page.route('**/api/word/packs?**', (route) => fulfillWordPacks(route));
    await page.goto('/');

    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    const searchInput = page.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await searchInput.fill('no-match');
    await searchInput.press('Enter');

    await expect(page.getByRole('heading', { name: '検索条件に一致するWordPackがありません' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '最近開いたWordPack' })).toHaveCount(0);
    await expect(page.getByRole('list', { name: '現在適用中の条件' })).toContainText(
      '検索: no-match（部分一致）',
    );
    await runA11yCheck(page);

    const clearSearchButton = page.getByRole('button', { name: '検索を解除' });
    const clearSearchBox = await clearSearchButton.boundingBox();
    const viewport = page.viewportSize();
    expect(clearSearchBox).not.toBeNull();
    expect(viewport).not.toBeNull();
    expect(clearSearchBox!.y + clearSearchBox!.height).toBeLessThanOrEqual(viewport!.height);

    await clearSearchButton.click();
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    await expect(searchInput).toHaveValue('');

    await page.getByRole('button', { name: '公開中 0' }).click();
    await expect(page.getByRole('heading', { name: '絞り込み条件に一致するWordPackがありません' })).toBeVisible();
    await expect(page.getByRole('list', { name: '現在適用中の条件' })).toContainText(
      '公開状態: 公開中',
    );
    await page.getByRole('button', { name: '絞り込みを解除' }).click();
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
  });

  test('初回読み込み失敗を空状態と区別して再試行できる', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    let shouldFail = true;
    await page.route('**/api/word/packs?**', (route) => {
      if (shouldFail) {
        return route.fulfill(
          json({ detail: '一時的にWordPack一覧を取得できません。' }, 503),
        );
      }
      return fulfillWordPacks(route);
    });
    await page.goto('/');

    await expect(page.getByRole('heading', { name: 'WordPack一覧を読み込めませんでした' })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText('保存済みデータが削除されたわけではありません。');
    await expect(page.getByRole('heading', { name: '保存済みWordPackはまだありません' })).toHaveCount(0);
    await runA11yCheck(page);

    shouldFail = false;
    await page.getByRole('button', { name: 'もう一度読み込む' }).click();
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
  });

  test('再読み込み中と失敗後も前回の一覧を保持する', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    let shouldHoldRefresh = false;
    let releaseRefresh: (() => void) | null = null;
    const refreshGate = new Promise<void>((resolve) => {
      releaseRefresh = resolve;
    });
    await page.route('**/api/word/packs?**', async (route) => {
      if (!shouldHoldRefresh) return fulfillWordPacks(route);
      await refreshGate;
      return route.fulfill(
        json({ detail: '一時的にWordPack一覧を取得できません。' }, 503),
      );
    });
    await page.goto('/');

    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    shouldHoldRefresh = true;
    await page.getByRole('button', { name: '更新', exact: true }).click();
    await expect(page.getByText('WordPack一覧を更新中')).toBeVisible();
    await expect(page.getByTestId('wp-card')).toHaveCount(2);

    releaseRefresh?.();
    await expect(page.getByRole('heading', { name: '最新の一覧に更新できませんでした' })).toBeVisible();
    await expect(page.getByRole('alert')).toContainText(
      '前回取得したWordPackを表示しています。画面上の内容は最新でない可能性があります。',
    );
    await expect(page.getByTestId('wp-card')).toHaveCount(2);
    await runA11yCheck(page);
  });

  test('狭幅でも状態説明と回復操作が横にはみ出さない', async ({ context, page }) => {
    await prepareAuthenticatedPage(context, page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.route('**/api/word/packs?**', (route) => fulfillWordPacks(route));
    await page.goto('/');

    const searchInput = page.getByRole('searchbox', { name: '保存済みWordPackを検索' });
    await searchInput.fill('no-match');
    await searchInput.press('Enter');
    const clearButton = page.getByRole('button', { name: '検索を解除' });
    await expect(clearButton).toBeVisible();

    const layout = await page.evaluate(() => {
      const button = Array.from(document.querySelectorAll('button'))
        .find((element) => element.textContent?.trim() === '検索を解除');
      return {
        documentClientWidth: document.documentElement.clientWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        buttonHeight: button?.getBoundingClientRect().height ?? 0,
      };
    });
    expect(layout.documentScrollWidth).toBeLessThanOrEqual(layout.documentClientWidth + 1);
    expect(layout.buttonHeight).toBeGreaterThanOrEqual(44);
    await runA11yCheck(page);
  });
});
