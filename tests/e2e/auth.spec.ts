import { test, expect } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const EMPTY_LIST_RESPONSE = { items: [], total: 0 };

test.describe('認証導線', () => {
  test('Cookie 注入で OAuth ポップアップを使わずにログイン状態へ遷移できる', async ({ page, context }) => {
    await seedAuthenticatedSession(context, page);
    await mockConfig(page, { requestTimeoutMs: 20000 });

    await page.route('**/api/word/packs?*', (route) => route.fulfill(json(EMPTY_LIST_RESPONSE)));
    // Reader移動後の一覧も固定し、テスト用Cookieを実backendへ送って401になる経路を除外する。
    await page.route(
      (url) => url.pathname === '/api/article',
      (route) => route.fulfill(json({ ...EMPTY_LIST_RESPONSE, limit: 20, offset: 0 })),
    );

    await test.step('Given: 認証 Cookie と localStorage がセット済み', async () => {
      await page.goto('/');
    });

    await test.step('When: アプリを初期表示する', async () => {
      const sidebar = page.getByLabel('アプリ内共通メニュー');
      await expect(sidebar).toBeVisible();
      await expect(sidebar).toHaveAttribute('aria-hidden', 'false');
    });

    await test.step('Then: ログイン済み UI が表示される', async () => {
      await page.waitForURL('**/lexicon', { waitUntil: 'domcontentloaded' });
      await page.waitForLoadState('networkidle');
      // なぜ: ログイン状態の操作は常時表示のサイドバー下部に集約しているため。
      await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
      await expect(
        page.getByRole('heading', { name: 'WordPack', level: 1, includeHidden: true }),
      ).toHaveCount(1);
    });

    await test.step('Then: 常時表示サイドバーで aria-hidden-focus の a11y 違反がない', async () => {
      await runA11yCheck(page);
    });

    await test.step('Then: main ランドマークと h1 の a11y 違反がない', async () => {
      await runA11yCheck(page, { rules: ['landmark-one-main', 'page-has-heading-one'] });
    });

    await test.step('Then: キーボード操作でサイドバーから移動できる', async () => {
      const readerButton = page.getByRole('button', { name: '文章インポート' });
      await readerButton.focus();
      await expect(readerButton).toBeFocused();
      await page.keyboard.press('Enter');
      await expect(page.getByRole('heading', { name: 'Reader' })).toBeVisible();
      await expect
        .poll(async () =>
          readerButton.evaluate((button) => {
            const rect = button.getBoundingClientRect();
            const topElement = document.elementFromPoint(
              rect.left + rect.width / 2,
              rect.top + rect.height / 2,
            );
            return topElement === button || button.contains(topElement);
          }),
        )
        .toBe(true);
    });
  });

  test('logout通信の到達結果が不明でも HttpOnly Cookie はJSから見えず後続リクエストへ送られる', async ({
    page,
    context,
  }) => {
    const now = Date.now();
    const cookieFixtures = [
      { name: 'wp_session', value: 'browser-user-session' },
      { name: '__session', value: 'browser-alias-session' },
      { name: 'wp_guest', value: 'browser-guest-session' },
    ];
    await context.addCookies(
      cookieFixtures.map(({ name, value }) => ({
        name,
        value,
        domain: '127.0.0.1',
        path: '/',
        httpOnly: true,
        sameSite: 'Lax' as const,
        expires: Math.floor((now + 60 * 60 * 1000) / 1000),
      })),
    );
    await mockConfig(page);

    // route.abort はbackend到達前の通信失敗を模倣する。server-side revokeの証拠には使わない。
    await page.route('**/api/auth/logout', (route) => route.abort('failed'));
    let protectedCookieHeader = '';
    await page.route('**/api/word/packs*', async (route) => {
      protectedCookieHeader = route.request().headers().cookie ?? '';
      await route.fulfill(json({ detail: 'session invalid' }, 401));
    });
    await page.goto('/');

    const logoutOutcome = await page.evaluate(async () => {
      try {
        const response = await fetch('/api/auth/logout', {
          method: 'POST',
          credentials: 'include',
        });
        return { outcome: 'response', status: response.status };
      } catch {
        return { outcome: 'unknown' };
      }
    });
    expect(logoutOutcome).toEqual({ outcome: 'unknown' });

    // HttpOnly Cookieは document.cookie に露出せず、JSの削除fallbackでは消えない。
    const documentCookie = await page.evaluate(() => document.cookie);
    for (const { name } of cookieFixtures) {
      expect(documentCookie).not.toContain(`${name}=`);
    }

    const protectedResponse = await page.evaluate(async () => {
      const response = await fetch('/api/word/packs', {
        credentials: 'include',
      });
      return { status: response.status };
    });
    expect(protectedResponse).toEqual({ status: 401 });
    expect(protectedCookieHeader).toContain('wp_session=browser-user-session');
    expect(protectedCookieHeader).toContain('__session=browser-alias-session');
    expect(protectedCookieHeader).toContain('wp_guest=browser-guest-session');

    const browserCookies = await context.cookies();
    expect(
      browserCookies
        .filter(({ name }) =>
          cookieFixtures.some((fixture) => fixture.name === name),
        )
        .map(({ name, value, httpOnly }) => ({ name, value, httpOnly }))
        .sort((left, right) => left.name.localeCompare(right.name)),
    ).toEqual(
      cookieFixtures
        .map(({ name, value }) => ({ name, value, httpOnly: true }))
        .sort((left, right) => left.name.localeCompare(right.name)),
    );
  });

  test('ゲストセッション再発行の応答を受け取るまでログアウトを送らない', async ({
    page,
    context,
  }) => {
    const events: string[] = [];
    let releaseIssuance!: () => void;
    let releaseLogout!: () => void;
    const issuanceRelease = new Promise<void>((resolve) => {
      releaseIssuance = resolve;
    });
    const logoutRelease = new Promise<void>((resolve) => {
      releaseLogout = resolve;
    });
    let protectedCookieHeader = '';
    let protectedShould401 = false;

    await page.addInitScript(() => {
      window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    });
    await mockConfig(page);
    await page.route('**/api/auth/guest', async (route) => {
      events.push('issuance-request');
      await issuanceRelease;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Set-Cookie': 'wp_guest=issued-browser-guest; HttpOnly; Path=/; SameSite=Lax',
        },
        body: JSON.stringify({ mode: 'guest' }),
      });
      events.push('issuance-response');
    });
    await page.route('**/api/auth/logout', async (route) => {
      events.push('logout-request');
      await logoutRelease;
      await route.fulfill({
        status: 204,
        headers: {
          'Set-Cookie': 'wp_guest=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax',
        },
      });
      events.push('logout-response');
    });
    await page.route('**/api/word/packs*', async (route) => {
      protectedCookieHeader = route.request().headers().cookie ?? '';
      const status = protectedShould401 ? 401 : 200;
      await route.fulfill(
        status === 200
          ? json(EMPTY_LIST_RESPONSE)
          : json({ detail: 'session invalid' }, status),
      );
    });
    await page.goto('/');

    const logoutButton = page.getByRole('button', { name: 'ログアウト' }).first();
    await expect(logoutButton).toBeVisible();
    await page.evaluate(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));
    });
    await expect.poll(() => events).toContain('issuance-request');
    await expect(logoutButton).toBeEnabled();

    // 実UIのログアウト操作を発行中に開始し、発行応答が届くまでPOSTが出ないことを確認する。
    await logoutButton.click();
    await page.waitForTimeout(100);
    expect(events).not.toContain('logout-request');

    releaseIssuance();
    await expect.poll(() => events).toContain('issuance-response');
    expect(
      (await context.cookies()).filter(({ name }) => name === 'wp_guest'),
    ).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: 'wp_guest', value: 'issued-browser-guest', httpOnly: true }),
      ]),
    );
    await expect.poll(() => events).toContain('logout-request');

    releaseLogout();
    await expect(page.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    expect(events).toEqual([
      'issuance-request',
      'issuance-response',
      'logout-request',
      'logout-response',
    ]);

    // 401はrouteの合成応答、Cookieヘッダー空は実ブラウザの削除結果として記録する。
    protectedShould401 = true;
    const protectedResponse = await page.evaluate(async () => {
      const response = await fetch('/api/word/packs', { credentials: 'include' });
      return { status: response.status };
    });
    expect(protectedResponse).toEqual({ status: 401 });
    expect(protectedCookieHeader).not.toContain('wp_guest=');
    expect(protectedCookieHeader).not.toContain('wp_session=');
    expect(protectedCookieHeader).not.toContain('__session=');
    expect((await context.cookies()).filter(({ name }) => name === 'wp_guest')).toEqual([]);
  });

  test('ログアウト確認中はpolite statusを示し、失敗応答後にassertive alertへ遷移する', async ({ page }) => {
    let releaseLogout!: () => void;
    let logoutRequestStarted = false;
    const logoutRelease = new Promise<void>((resolve) => {
      releaseLogout = resolve;
    });

    await page.addInitScript(() => {
      window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({
        authMode: 'authenticated',
        user: { google_sub: 'pending-logout-user', email: 'pending@example.test', display_name: 'Pending Logout User' },
      }));
      window.localStorage.setItem('wordpack.logout.v1', JSON.stringify({ outcome: 'failed' }));
    });
    await mockConfig(page);
    await page.route('**/api/auth/logout', async (route) => {
      logoutRequestStarted = true;
      await logoutRelease;
      await route.fulfill(json({ detail: 'temporary failure' }, 503));
    });
    await page.goto('/');

    const retryButton = page.getByRole('button', { name: 'ログアウトを再試行' });
    await expect(retryButton).toBeVisible();
    await retryButton.click();
    await expect.poll(() => logoutRequestStarted).toBe(true);

    await expect(page.getByRole('status')).toBeVisible();
    await expect(page.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    await expect(page.getByRole('status')).toContainText('ログアウトしています');
    await expect(page.getByRole('alert')).toHaveCount(0);

    releaseLogout();
    const failureAlert = page.getByRole('alert');
    await expect(failureAlert).toBeVisible();
    await expect(failureAlert).toHaveAttribute('aria-live', 'assertive');
    await expect(failureAlert).toContainText('ログアウトに失敗しました');
    await expect(page.getByRole('status')).toHaveCount(0);
  });
});
