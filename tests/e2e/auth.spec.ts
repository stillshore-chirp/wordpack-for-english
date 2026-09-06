import { test, expect, type Page } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const EMPTY_LIST_RESPONSE = { items: [], total: 0 };

// OAuth本体へ接続せず、実際の GoogleLogin コンポーネントから AuthProvider の
// signIn callbackまでを通すための最小 GIS fixture。資格情報はテスト専用の合成値。
const SYNTHETIC_GSI_SCRIPT = `
(() => {
  const fixture = window.__wordpackGsiFixture || { callback: null };
  fixture.issue = () => {
    const current = window.__wordpackGsiFixture;
    if (current && current.callback) current.callback({ credential: 'synthetic-p1-id-token', client_id: 'e2e-client', select_by: 'button' });
  };
  window.__wordpackGsiFixture = fixture;
  /*
   * StrictMode may load the GIS script twice during development. Keep the
   * callback on the stable fixture object so a late script cannot hide it.
   */
  window.google = {
    accounts: {
      id: {
        initialize(options) {
          window.__wordpackGsiFixture.callback = options.callback;
        },
        renderButton(container) {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = 'Googleでログイン';
          button.setAttribute('aria-label', 'Googleでログイン');
          button.addEventListener('click', () => window.__wordpackGsiFixture.issue());
          container.replaceChildren(button);
        },
        prompt() {},
        cancel() {},
      },
    },
  };
})();
`;

const blockLocalStorage = async (page: Page): Promise<void> => {
  await page.addInitScript(() => {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get() {
        throw new DOMException('localStorage blocked for this browser lane', 'SecurityError');
      },
    });
  });
};

const installGsiFixture = async (page: Page): Promise<void> => {
  await page.route('https://accounts.google.com/gsi/client*', (route) =>
    route.fulfill({ status: 200, contentType: 'application/javascript', body: SYNTHETIC_GSI_SCRIPT }),
  );
};

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

  test('別タブの保留中ゲスト発行はログアウト完了後に追従失効する', async ({ browser }) => {
    const context = await browser.newContext();
    const pageA = await context.newPage();
    const pageB = await context.newPage();
    const events: string[] = [];
    let releaseIssuance!: () => void;
    let issuanceDelivered = false;
    let followupCookieHeader = '';
    const issuanceRelease = new Promise<void>((resolve) => {
      releaseIssuance = resolve;
    });

    await pageA.addInitScript(() => {
      window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    });
    await mockConfig(pageA);
    await mockConfig(pageB);
    // Tab A is a stable guest consumer. Tab B reaches the real backend with no cookie,
    // receives 401, and starts the actual AuthProvider guest reissue flow below.
    await pageA.route('**/api/word/packs*', (route) => route.fulfill(json(EMPTY_LIST_RESPONSE)));
    await pageB.route('**/api/auth/guest', async (route) => {
      events.push('B:guest-request');
      await issuanceRelease;
      // The CI smoke backend has no Firestore emulator. Keep the delayed
      // Set-Cookie/browser ordering real while the server-side revoke/401
      // contract remains covered by the local backend evidence and backend gate.
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          'Set-Cookie': 'wp_guest=synthetic-browser-guest; HttpOnly; Path=/; SameSite=Lax',
        },
        body: JSON.stringify({ mode: 'guest' }),
      });
      issuanceDelivered = true;
      events.push('B:guest-response');
    });
    await pageA.route('**/api/auth/logout', async (route) => {
      events.push('A:logout-request');
      await route.continue();
    });
    await pageB.route('**/api/auth/logout', async (route) => {
      if (!issuanceDelivered) {
        throw new Error('Tab B sent follow-up logout before the delayed guest response arrived');
      }
      followupCookieHeader = route.request().headers().cookie ?? '';
      events.push('B:logout-request');
      await route.continue();
    });
    for (const [tab, page] of [['A', pageA] as const, ['B', pageB] as const]) {
      page.on('response', (response) => {
        const url = new URL(response.url());
        if (!url.pathname.startsWith('/api/auth/')) return;
        events.push(`${tab}:${response.request().method()}:${url.pathname}:${response.status()}`);
      });
    }

    await pageA.goto('/');
    const logoutA = pageA.getByRole('button', { name: 'ログアウト' }).first();
    await expect(logoutA).toBeVisible();

    await pageB.goto('/');
    await expect.poll(() => events).toContain('B:guest-request');
    await expect(pageB.getByRole('button', { name: 'ログアウト' }).first()).toBeVisible();

    // The shared storage event confirms Tab A's server logout while Tab B's issuance
    // request is still pending. No completion UI or follow-up logout may happen yet.
    await logoutA.click();
    await expect.poll(() => events).toContain('A:logout-request');
    await expect.poll(() => events).toContain('A:POST:/api/auth/logout:204');
    await pageB.waitForTimeout(100);
    expect(events).not.toContain('B:logout-request');
    await expect(pageB.getByRole('heading', { name: 'WordPack にサインイン' })).toHaveCount(0);

    releaseIssuance();
    await expect.poll(() => events).toContain('B:guest-response');
    await expect.poll(() => events).toContain('B:logout-request');
    expect(events.indexOf('B:guest-response')).toBeLessThan(events.indexOf('B:logout-request'));
    expect(followupCookieHeader).toContain('wp_guest=');

    await expect.poll(async () => {
      const cookies = await context.cookies();
      return cookies.filter(({ name }) => ['wp_guest', '__session', 'wp_session'].includes(name));
    }).toEqual([]);
    await expect.poll(async () => pageB.evaluate(() => localStorage.getItem('wordpack.logout.v1'))).toBe(null);

    const protectedResponse = await pageB.evaluate(async () => {
      const response = await fetch('/api/word/packs?limit=1&offset=0', { credentials: 'include' });
      return { status: response.status };
    });
    expect(protectedResponse).toEqual({ status: 401 });
    await expect(pageB.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    const followupCookieNames = followupCookieHeader
      .split(';')
      .map((part) => part.trim().split('=', 1)[0])
      .filter(Boolean)
      .sort();
    await test.info().attach('cross-tab-logout-order.json', {
      body: JSON.stringify({
        events,
        followupCookieNames,
        protectedResponse,
        finalBrowserCookieNames: (await context.cookies()).map(({ name }) => name).sort(),
        finalLogoutMarker: await pageB.evaluate(() => localStorage.getItem('wordpack.logout.v1')),
      }, null, 2),
      contentType: 'application/json',
    });
    await context.close();
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

  test('localStorage unavailable時も別タブへ失敗状態を伝え、再試行204で両タブを確定する', async ({ browser }) => {
    const context = await browser.newContext();
    const pageA = await context.newPage();
    const pageB = await context.newPage();
    const events: string[] = [];
    let authRequestCount = 0;
    let logoutRequestCount = 0;
    let pageBLogoutRequestCount = 0;

    for (const [label, page] of [['A', pageA] as const, ['B', pageB] as const]) {
      await blockLocalStorage(page);
      await installGsiFixture(page);
      await mockConfig(page, { googleClientId: 'e2e-client' });
      page.on('request', (request) => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/auth/')) {
          events.push(`${label}:request:${request.method()}:${url.pathname}`);
        }
      });
      page.on('response', (response) => {
        const url = new URL(response.url());
        if (url.pathname.startsWith('/api/auth/')) {
          events.push(`${label}:response:${response.status()}:${url.pathname}`);
        }
      });
      await page.route('**/api/auth/google', async (route) => {
        authRequestCount += 1;
        events.push(`${label}:google-request`);
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: {
            'Set-Cookie': `wp_session=synthetic-p1-session-${label.toLowerCase()}; HttpOnly; Path=/; SameSite=Lax`,
          },
          body: JSON.stringify({
            user: {
              google_sub: 'synthetic-p1-user',
              email: 'p1-user@example.test',
              display_name: 'P1 Synthetic User',
            },
          }),
        });
        events.push(`${label}:google-response`);
      });
      // AppShellの初期データ取得を固定し、認証状態の伝播だけを観測する。
      await page.route(
        (url) => url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/auth/') && url.pathname !== '/api/config',
        (route) => route.fulfill(json(EMPTY_LIST_RESPONSE)),
      );
    }

    await pageA.route('**/api/auth/logout', async (route) => {
      logoutRequestCount += 1;
      events.push(`A:logout-request-${logoutRequestCount}`);
      await route.fulfill(
        logoutRequestCount === 2
          ? {
              ...json({ detail: 'temporary failure' }, 503),
              headers: {},
            }
          : {
              status: 204,
              headers: logoutRequestCount >= 3
                ? { 'Set-Cookie': 'wp_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax' }
                : {},
            },
      );
      events.push(`A:logout-response-${logoutRequestCount}`);
    });
    await pageB.route('**/api/auth/logout', async (route) => {
      pageBLogoutRequestCount += 1;
      events.push(`B:logout-request-${pageBLogoutRequestCount}`);
      await route.fulfill({
        status: 204,
        headers: pageBLogoutRequestCount >= 2
          ? { 'Set-Cookie': 'wp_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax' }
          : {},
      });
    });

    await pageA.goto('/');
    await pageB.goto('/');
    for (const page of [pageA, pageB]) {
      await expect(page.getByRole('button', { name: 'ログアウトを再試行' })).toBeVisible();
      await expect
        .poll(() => page.evaluate(() => {
          try {
            void window.localStorage;
            return 'readable';
          } catch {
            return 'blocked';
          }
        }))
        .toBe('blocked');
    }

    // 新規のsession-only tabは、過去のlogout通知を受け取れないため初期unknownになる。
    // Aで実際のretry 204を完了すると、同じcontextのBへconfirmed receiptが配送される。
    await pageA.getByRole('button', { name: 'ログアウトを再試行' }).click();
    await expect.poll(() => logoutRequestCount).toBe(1);
    await expect(pageA.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    await expect(pageB.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    expect(pageBLogoutRequestCount).toBe(0);

    // GIS callback → AuthProvider.signIn → synthetic /api/auth/google の実UI経路。
    await pageA.getByRole('button', { name: 'Googleでログイン' }).click();
    await expect(pageA.getByRole('button', { name: 'ログアウト' }).first()).toBeVisible();
    await pageB.getByRole('button', { name: 'Googleでログイン' }).click();
    await expect(pageB.getByRole('button', { name: 'ログアウト' }).first()).toBeVisible();
    await expect.poll(() => authRequestCount).toBe(2);
    await expect.poll(async () => (await context.cookies()).filter(({ name }) => name === 'wp_session').length).toBe(1);

    await pageA.getByRole('button', { name: 'ログアウト' }).first().click();
    await expect.poll(() => logoutRequestCount).toBe(2);
    await expect.poll(() => events).toContain('A:logout-response-2');
    await expect(pageA.getByRole('alert')).toContainText('ログアウトに失敗しました');
    await expect(pageB.getByRole('button', { name: 'ログアウトを再試行' })).toBeVisible();
    await expect(pageB.getByRole('alert')).toContainText('ログアウトに失敗しました');
    expect(pageBLogoutRequestCount).toBe(0);

    // 失敗通知より後に開いた新規tabも、過去のBroadcastChannel通知を受け取れないため
    // sessionStorageの確認receiptがなくunknownで止まり、再試行を要求する。
    const pageC = await context.newPage();
    await blockLocalStorage(pageC);
    await installGsiFixture(pageC);
    await mockConfig(pageC, { googleClientId: 'e2e-client' });
    await pageC.goto('/');
    await expect(pageC.getByRole('alert')).toContainText('ログアウトの結果を確認できませんでした');
    await expect(pageC.getByRole('button', { name: 'ログアウトを再試行' })).toBeVisible();

    for (const page of [pageA, pageB]) {
      await expect(page.locator('body')).not.toContainText('p1-user@example.test');
      await expect(page.locator('body')).not.toContainText('P1 Synthetic User');
      await expect.poll(() => page.evaluate(() => ({
        auth: window.sessionStorage.getItem('wordpack.auth.v1'),
        recovery: JSON.parse(window.sessionStorage.getItem('wordpack.logout.v1') || 'null')?.outcome ?? null,
      }))).toEqual({ auth: null, recovery: 'failed' });
    }

    await pageA.getByRole('button', { name: 'ログアウトを再試行' }).click();
    await expect.poll(() => logoutRequestCount).toBe(3);
    await expect.poll(() => events).toContain('A:logout-response-3');
    await expect(pageA.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    await expect(pageB.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    await expect(pageC.getByRole('heading', { name: 'WordPack にサインイン' })).toBeVisible();
    await expect(pageA.getByRole('button', { name: 'ログアウトを再試行' })).toHaveCount(0);
    await expect(pageB.getByRole('button', { name: 'ログアウトを再試行' })).toHaveCount(0);
    // Aのconfirmed通知後は、Bが自身の発行履歴を持つ場合にだけ再失効を
    // 送る実装を許容する。失敗状態の受信中に自動retryしないことは上で固定する。
    expect(pageBLogoutRequestCount).toBeLessThanOrEqual(1);
    if (pageBLogoutRequestCount === 1) {
      expect(events.indexOf('B:logout-request-1')).toBeGreaterThan(events.indexOf('A:logout-response-2'));
    }

    for (const page of [pageA, pageB]) {
      await expect.poll(() => page.evaluate(() => ({
        auth: window.sessionStorage.getItem('wordpack.auth.v1'),
        recovery: JSON.parse(window.sessionStorage.getItem('wordpack.logout.v1') || 'null')?.outcome ?? null,
      }))).toEqual({ auth: null, recovery: null });
    }
    await expect.poll(async () => (await context.cookies()).filter(({ name }) => name === 'wp_session')).toEqual([]);
    await test.info().attach('cross-tab-session-storage-blocked.json', {
      body: JSON.stringify({
        events,
        authRequestCount,
        logoutRequestCount,
        pageBLogoutRequestCount,
        finalCookieNames: (await context.cookies()).map(({ name }) => name).sort(),
      }, null, 2),
      contentType: 'application/json',
    });
    await context.close();
  });
});
