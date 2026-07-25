import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';
import {
  json,
  mockConfig,
  runA11yCheck,
  seedAuthenticatedSession,
} from './helpers';

const wordPacks = [
  {
    id: 'wp:e2e:alpha',
    lemma: 'alpha',
    sense_title: '最初の文字・第一段階',
    created_at: '2024-01-10T09:15:00Z',
    updated_at: '2024-01-12T12:00:00Z',
    is_empty: false,
    guest_public: true,
    examples_count: {
      Dev: 3,
      CS: 1,
      LLM: 0,
      Business: 2,
      Common: 4,
    },
    checked_only_count: 1,
    learned_count: 2,
  },
  {
    id: 'wp:e2e:bravo',
    lemma: 'bravo',
    sense_title: '称賛を表す語',
    created_at: '2024-01-08T08:30:00Z',
    updated_at: '2024-01-11T18:05:00Z',
    is_empty: true,
    guest_public: false,
    examples_count: {
      Dev: 0,
      CS: 0,
      LLM: 0,
      Business: 0,
      Common: 0,
    },
    checked_only_count: 0,
    learned_count: 0,
  },
  {
    id: 'wp:e2e:charlie',
    lemma: 'charlie',
    sense_title: '無線通話表のC',
    created_at: '2024-01-05T03:20:00Z',
    updated_at: '2024-01-06T11:10:00Z',
    is_empty: false,
    guest_public: false,
    examples_count: {
      Dev: 5,
      CS: 0,
      LLM: 0,
      Business: 1,
      Common: 2,
    },
    checked_only_count: 3,
    learned_count: 1,
  },
];

const mockWordPacks = async (page: Page) => {
  await page.route('**/api/word/packs?**', (route) =>
    route.fulfill(
      json({
        items: wordPacks,
        total: wordPacks.length,
        limit: 200,
        offset: 0,
      }),
    ),
  );
};

test.describe('Shelves', () => {
  test.beforeEach(async ({ context, page }) => {
    await seedAuthenticatedSession(context, page);
    await mockConfig(page, {
      requestTimeoutMs: 20000,
      sessionAuthDisabled: false,
    });
    await mockWordPacks(page);
    await page.emulateMedia({ reducedMotion: 'reduce' });
  });

  test('棚を開くと対象一覧へ移動し、選択結果を通知する', async ({ page }) => {
    await page.goto('/shelves');

    const moveButton = page.getByRole('button', {
      name: '「最近更新」棚のWordPack一覧へ移動',
    });
    await expect(moveButton).toBeVisible();
    await moveButton.click();

    const results = page.getByRole('region', { name: '最近更新' });
    const heading = results.getByRole('heading', {
      name: '最近更新',
      level: 3,
    });
    await expect(heading).toBeFocused();
    await expect(results.getByRole('status')).toContainText(
      '最近更新のWordPackを3件表示しました。',
    );
    const position = await heading.evaluate((element) => {
      const rect = element.getBoundingClientRect();
      return {
        bottom: rect.bottom,
        top: rect.top,
        viewportHeight: window.innerHeight,
      };
    });
    expect(position.top).toBeGreaterThanOrEqual(0);
    expect(position.bottom).toBeLessThanOrEqual(position.viewportHeight);

    const search = page.getByRole('searchbox', {
      name: '棚とWordPackを検索',
    });
    await search.fill('alpha');
    await expect(search).toBeFocused();
    await expect(search).toHaveValue('alpha');
    await runA11yCheck(page);
  });

  test('棚名検索、該当なし、検索解除を同じ対象範囲で扱う', async ({ page }) => {
    await page.goto('/shelves');

    const search = page.getByRole('searchbox', {
      name: '棚とWordPackを検索',
    });
    await page.getByRole('heading', { name: 'Shelves', level: 2 }).click();
    await page.keyboard.press('Meta+K');
    await expect(search).toBeFocused();

    await search.fill('未生成');
    await expect(
      page.getByRole('button', {
        name: '「未生成」棚のWordPack一覧へ移動',
      }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('region', { name: '未生成' })).toContainText(
      'bravo',
    );

    await search.fill('一致しない検索語');
    await expect(
      page.getByText(
        '「一致しない検索語」に一致する棚やWordPackはありません。',
      ),
    ).toBeVisible();
    await expect(page.locator('#shelves-results')).toHaveCount(0);

    await page.getByRole('button', { name: '検索を解除' }).click();
    await expect(search).toHaveValue('');
    await expect(search).toBeFocused();
  });

  test('狭幅と文字拡大でも主要操作がリフローし、横方向に欠けない', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/shelves');
    await page.getByRole('button', { name: 'メニューを開く' }).click();
    await page.getByRole('button', { name: 'メニューを閉じる' }).click();
    await page.getByRole('button', {
      name: '「未生成」棚のWordPack一覧を表示',
    }).click();
    await expect(
      page
        .getByRole('region', { name: '未生成' })
        .getByRole('heading', { name: '未生成', level: 3 }),
    ).toBeFocused();

    const narrowOverflow = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(narrowOverflow.scrollWidth).toBeLessThanOrEqual(
      narrowOverflow.clientWidth + 1,
    );

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.evaluate(() => {
      document.documentElement.style.fontSize = '200%';
    });
    const enlargedOverflow = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(enlargedOverflow.scrollWidth).toBeLessThanOrEqual(
      enlargedOverflow.clientWidth + 1,
    );
    await expect(
      page.getByRole('button', {
        name: '「未生成」棚のWordPack一覧へ移動',
      }),
    ).toBeVisible();
    await runA11yCheck(page);
  });

  test('初回取得失敗を空棚にせず再試行できる', async ({ page }) => {
    await page.unroute('**/api/word/packs?**');
    let requestCount = 0;
    await page.route('**/api/word/packs?**', (route) => {
      requestCount += 1;
      if (requestCount <= 2) {
        return route.fulfill(
          json({ detail: '一時的に取得できません' }, 503),
        );
      }
      return route.fulfill(
        json({
          items: wordPacks,
          total: wordPacks.length,
          limit: 200,
          offset: 0,
        }),
      );
    });
    await page.goto('/shelves');

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('棚を表示できません');
    await expect(page.getByLabel('棚の集計')).toHaveCount(0);
    await expect(
      page.getByRole('list', { name: '自動分類の棚一覧' }),
    ).toHaveCount(0);

    await page.getByRole('button', { name: '一覧を再読み込み' }).click();
    await expect(
      page.getByRole('list', { name: '自動分類の棚一覧' }),
    ).toBeVisible();
  });
});
