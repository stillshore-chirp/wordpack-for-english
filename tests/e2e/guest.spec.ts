import { test, expect } from '@playwright/test';
import { json, mockConfig, ignoreRoute, runA11yCheck } from './helpers';

test.describe('ゲストモード', () => {
  test('ログイン画面からゲスト閲覧へ遷移できる', async ({ page }) => {
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'guest', sense_title: 'guest' }], total: 1 })),
    );

    await test.step('Given: 未認証のログイン画面が表示されている', async () => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      // ログイン見出しは App.tsx の login-title と一致させ、UI文言の正を明確にする。
      await expect(page.getByRole('heading', { name: 'WordPack にサインイン', level: 2 })).toBeVisible({ timeout: 15000 });
      await expect(page.getByRole('button', { name: 'ゲスト閲覧モード' })).toBeVisible();
    });

    await test.step('Then: ログイン画面で a11y 違反がない', async () => {
      await runA11yCheck(page);
    });

    await test.step('Then: main ランドマークと h1 の a11y 違反がない', async () => {
      await runA11yCheck(page, { rules: ['landmark-one-main', 'page-has-heading-one'] });
    });

    await test.step('When: キーボードでゲスト閲覧モードを選択する', async () => {
      const guestButton = page.getByRole('button', { name: 'ゲスト閲覧モード' });

      /**
       * Googleログインボタンは外部SDKが iframe/Shadow DOM を注入するため、E2E では
       * 「ゲスト導線がキーボードで到達・実行できる」ことを観測点にする。
       */
      await page.keyboard.press('Tab');
      // 直前のフォーカス位置は環境依存のため、確実にゲストボタンへフォーカスして Enter で実行する。
      await guestButton.focus();
      await expect(guestButton).toBeFocused();
      await page.keyboard.press('Enter');
    });

    await test.step('Then: ゲストバッジと操作制限が表示される', async () => {
      await expect(page.getByText('ゲスト閲覧モード')).toBeVisible();
      await expect(page.getByLabel('アプリ内共通メニュー')).toBeVisible();
      await expect(page.getByRole('button', { name: '作成を開始' })).toBeDisabled();
    });
  });

  test('モバイル下部ナビの高さを本文下余白に反映する', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'guest', sense_title: 'guest' }], total: 1 })),
    );

    await page.goto('/');
    await page.getByRole('button', { name: 'ゲスト閲覧モード' }).click();
    await expect(page.getByRole('navigation', { name: 'モバイル主要メニュー' })).toBeVisible();

    const metrics = await page.evaluate(() => {
      const nav = document.querySelector<HTMLElement>('.dictionary-bottom-nav');
      const shell = document.querySelector<HTMLElement>('.dictionary-shell');
      const mainInner = document.querySelector<HTMLElement>('.main-inner');
      if (!nav || !shell || !mainInner) {
        throw new Error('bottom nav metrics target is missing');
      }
      const navHeight = Math.ceil(nav.getBoundingClientRect().height);
      const reservedHeight = getComputedStyle(shell).getPropertyValue('--bottom-nav-height').trim();
      const paddingBottom = Number.parseFloat(getComputedStyle(mainInner).paddingBottom);
      return { navHeight, paddingBottom, reservedHeight };
    });

    expect(metrics.navHeight).toBeGreaterThan(0);
    expect(metrics.reservedHeight).toBe(`${metrics.navHeight}px`);
    expect(metrics.paddingBottom).toBeGreaterThanOrEqual(metrics.navHeight + 20);
  });

  test('Quiz本文と問題を全幅表示へ切り替えられる', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    const quiz = {
      id: 'quiz:focus',
      title_en: 'Reliable Reading Focus',
      format_profile: 'single_passage',
      generation_domain: 'technical',
      domain_intensity: 'standard',
      difficulty: 'medium',
      passages: [
        {
          id: 'p1',
          order: 1,
          kind: 'article',
          title: 'Dashboard review',
          body_en:
            'A product team noticed that a dashboard could distort decisions when it overlooked late records. They added a buffer and audited the query.\n\nThe reports became reliable again.',
          body_ja: 'プロダクトチームは、遅延レコードを見落とすとダッシュボードが判断を歪める可能性に気づきました。チームはバッファを追加し、クエリを監査しました。\n\nレポートは再び信頼できるものになりました。',
          speaker_labels: [],
        },
      ],
      notes_ja: '本文を読み、設問に答えてから根拠を確認します。',
      sections: [
        {
          id: 's1',
          order: 1,
          title: 'Section 1',
          description_ja: '本文全体の内容理解を問います。',
          passage_ids: ['p1'],
          questions: [
            {
              id: 'q1',
              order: 1,
              type: 'main_idea',
              prompt: 'What is the passage mainly about?',
              choices: [
                { id: 'A', text: 'A team making dashboard data more reliable' },
                { id: 'B', text: 'A team deleting all reports' },
                { id: 'C', text: 'A team replacing every customer record' },
                { id: 'D', text: 'A team ignoring audit results' },
              ],
              correct_choice_id: 'A',
              explanation: {
                explanation_ja: '本文はダッシュボードの信頼性を高める対応について述べています。',
                evidence_passage_id: 'p1',
                evidence_text: 'reports became reliable again',
                evidence_start: 129,
                evidence_end: 158,
                wrong_choice_explanations_ja: {},
                related_lemmas: ['reliable'],
              },
            },
          ],
        },
      ],
      related_word_packs: [],
      source_word_pack_ids: [],
      source_lemmas: ['reliable'],
      topic_seed: 'dashboard reliability',
      avoid_topics: [],
      llm_model: 'gpt-5.4-mini',
      llm_params: 'reasoning.effort=minimal;text.verbosity=medium',
      translation_alignment_version: 'deterministic_v1',
      created_at: '2026-01-02T03:04:00Z',
      updated_at: '2026-01-03T04:05:00Z',
      guest_public: true,
    };

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'reliable', sense_title: '信頼できる' }], total: 1 })),
    );
    await page.route('**/api/quiz?*', (route) =>
      route.fulfill(json({
        items: [
          {
            id: quiz.id,
            title_en: quiz.title_en,
            format_profile: quiz.format_profile,
            generation_domain: quiz.generation_domain,
            domain_intensity: quiz.domain_intensity,
            difficulty: quiz.difficulty,
            question_count: 1,
            passage_count: 1,
            source_lemmas: quiz.source_lemmas,
            created_at: quiz.created_at,
            updated_at: quiz.updated_at,
            guest_public: true,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      })),
    );
    await page.route('**/api/quiz/quiz%3Afocus', (route) => route.fulfill(json(quiz)));

    await page.goto('/');
    await page.getByRole('button', { name: 'ゲスト閲覧モード' }).click();
    await page.getByRole('button', { name: 'Quiz' }).click();
    await expect(page.getByRole('heading', { name: 'Reliable Reading Focus' })).toBeVisible();

    await page.getByText('日本語訳').click();
    await expect(page.locator('.quiz-passage-paragraph')).toHaveCount(2);
    await expect(page.locator('.quiz-translation__paragraph')).toHaveCount(2);
    const englishSecondSentence = page.getByRole('group', { name: '英文 2: 日本語訳と対応' });
    const japaneseSecondSentence = page.getByRole('group', { name: '日本語訳 2: 英文と対応' });
    await englishSecondSentence.hover();
    await expect(englishSecondSentence).toHaveClass(/is-active/);
    await expect(japaneseSecondSentence).toHaveClass(/is-active/);
    await page.getByRole('heading', { name: 'Reliable Reading Focus' }).hover();
    await japaneseSecondSentence.hover();
    await expect(englishSecondSentence).toHaveClass(/is-active/);
    await expect(japaneseSecondSentence).toHaveClass(/is-active/);
    await japaneseSecondSentence.click();
    await expect(englishSecondSentence).toHaveClass(/is-pinned/);
    await expect(japaneseSecondSentence).toHaveClass(/is-pinned/);
    await runA11yCheck(page);

    const generator = page.getByRole('form', { name: 'Quiz生成フォーム' });
    const savedList = page.getByRole('region', { name: '保存済みQuiz' });
    const detailPanel = page.getByRole('region', { name: '選択中Quiz詳細' });
    const generatedAt = page.locator('.quiz-detail-header time[datetime="2026-01-02T03:04:00Z"]');
    await expect(generator).toBeVisible();
    await expect(savedList).toBeVisible();
    await expect(savedList.locator('time[datetime="2026-01-02T03:04:00Z"]')).toBeVisible();
    await expect(generatedAt).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('quiz-detail-three-columns.png'), fullPage: true });

    const widthBefore = await detailPanel.evaluate((element) => element.getBoundingClientRect().width);
    const focusButton = page.getByRole('button', { name: '本文/問題を広げる' });
    await expect(focusButton).toHaveAttribute('aria-pressed', 'false');
    await focusButton.focus();
    await expect(focusButton).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(page.getByRole('button', { name: '3カラムに戻す' })).toHaveAttribute('aria-pressed', 'true');
    await expect(generator).toBeHidden();
    await expect(savedList).toBeHidden();
    await expect(generatedAt).toBeVisible();
    const widthAfter = await detailPanel.evaluate((element) => element.getBoundingClientRect().width);
    expect(widthAfter).toBeGreaterThan(widthBefore + 280);
    await runA11yCheck(page);
    await page.screenshot({ path: testInfo.outputPath('quiz-detail-focus.png'), fullPage: true });

    await page.getByRole('button', { name: '3カラムに戻す' }).click();
    await expect(page.getByRole('button', { name: '本文/問題を広げる' })).toHaveAttribute('aria-pressed', 'false');
    await expect(generator).toBeVisible();
    await expect(savedList).toBeVisible();

    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByRole('button', { name: '本文/問題を広げる' }).click();
    await expect(generator).toBeHidden();
    await expect(savedList).toBeHidden();
    const mobileOverflow = await page.evaluate(() => {
      const root = document.querySelector<HTMLElement>('#root');
      if (!root) {
        throw new Error('root is missing');
      }
      return {
        rootScrollWidth: root.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });
    expect(mobileOverflow.rootScrollWidth).toBeLessThanOrEqual(mobileOverflow.viewportWidth + 1);

    await page.evaluate(() => {
      document.documentElement.style.fontSize = '32px';
    });
    const scaledOverflow = await page.evaluate(() => {
      const root = document.querySelector<HTMLElement>('#root');
      if (!root) {
        throw new Error('root is missing');
      }
      return {
        rootScrollWidth: root.scrollWidth,
        bodyScrollWidth: document.body.scrollWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });
    expect(scaledOverflow.rootScrollWidth).toBeLessThanOrEqual(scaledOverflow.viewportWidth + 1);
    expect(scaledOverflow.bodyScrollWidth).toBeLessThanOrEqual(scaledOverflow.viewportWidth + 1);
    expect(scaledOverflow.documentScrollWidth).toBeLessThanOrEqual(scaledOverflow.viewportWidth + 1);
    await expect(generatedAt).toBeVisible();
    await runA11yCheck(page);
    await page.screenshot({ path: testInfo.outputPath('quiz-detail-mobile-200-percent.png'), fullPage: true });
  });

  test('デスクトップでページ全体をスクロールしてもサイドバー下部のユーザー操作が追従する', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'guest', sense_title: 'guest' }], total: 1 })),
    );

    await page.goto('/');
    await page.getByRole('button', { name: 'ゲスト閲覧モード' }).click();
    await expect(page.getByLabel('アプリ内共通メニュー')).toBeVisible();
    await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();

    await page.evaluate(() => {
      const content = document.querySelector<HTMLElement>('.dictionary-content');
      if (!content) {
        throw new Error('main content target is missing');
      }
      const spacer = document.createElement('div');
      spacer.setAttribute('data-testid', 'scroll-spacer');
      spacer.style.height = '1400px';
      content.appendChild(spacer);
    });

    const footer = page.locator('.sidebar-footer');
    const sidebar = page.getByLabel('アプリ内共通メニュー');
    const before = await footer.boundingBox();
    if (!before) {
      throw new Error('sidebar footer is missing');
    }

    await expect(sidebar).toHaveCSS('position', 'sticky');
    await page.evaluate(() => window.scrollTo(0, 620));
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(500);

    const after = await footer.boundingBox();
    if (!after) {
      throw new Error('sidebar footer disappeared after scrolling');
    }

    expect(Math.abs(after.y - before.y)).toBeLessThanOrEqual(1);
    expect(after.y).toBeGreaterThan(0);
    expect(after.y + after.height).toBeLessThanOrEqual(720);
    await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
  });

  test('デスクトップでサイドバーを折りたたんでも主要メニューを使える', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 720 });
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'guest', sense_title: 'guest' }], total: 1 })),
    );
    await page.route('**/api/word/examples?*', (route) =>
      route.fulfill(json({ items: [], total: 0, limit: 200, offset: 0 })),
    );

    await page.goto('/');
    await page.getByRole('button', { name: 'ゲスト閲覧モード' }).click();
    await expect(page.getByLabel('アプリ内共通メニュー')).toBeVisible();

    const before = await page.evaluate(() => {
      const sidebar = document.querySelector<HTMLElement>('.sidebar');
      const main = document.querySelector<HTMLElement>('.main-inner');
      if (!sidebar || !main) {
        throw new Error('layout metrics target is missing');
      }
      return {
        mainLeft: main.getBoundingClientRect().left,
        sidebarWidth: sidebar.getBoundingClientRect().width,
      };
    });

    const collapseButton = page.getByRole('button', { name: 'サイドメニューを折りたたむ' });
    await expect(collapseButton).toHaveAttribute('aria-expanded', 'true');
    await collapseButton.click();
    await expect(page.getByRole('button', { name: 'サイドメニューを展開' })).toHaveAttribute('aria-expanded', 'false');

    const after = await page.evaluate(() => {
      const sidebar = document.querySelector<HTMLElement>('.sidebar');
      const main = document.querySelector<HTMLElement>('.main-inner');
      const controls = document.querySelector<HTMLElement>('.sidebar-controls');
      const footer = document.querySelector<HTMLElement>('.sidebar-footer');
      if (!sidebar || !main || !controls || !footer) {
        throw new Error('collapsed layout metrics target is missing');
      }
      return {
        controlsDisplay: getComputedStyle(controls).display,
        footerDisplay: getComputedStyle(footer).display,
        mainLeft: main.getBoundingClientRect().left,
        sidebarWidth: sidebar.getBoundingClientRect().width,
      };
    });

    expect(after.sidebarWidth).toBeLessThan(before.sidebarWidth);
    expect(after.sidebarWidth).toBeLessThanOrEqual(80);
    expect(after.mainLeft).toBeLessThan(before.mainLeft);
    expect(after.controlsDisplay).toBe('none');
    expect(after.footerDisplay).toBe('none');

    await page.getByRole('button', { name: '例文一覧' }).click();
    await expect(page.getByRole('heading', { name: '例文一覧' })).toBeVisible();

    await page.getByRole('button', { name: 'サイドメニューを展開' }).click();
    await expect(page.getByRole('button', { name: 'サイドメニューを折りたたむ' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await expect(page.getByRole('button', { name: 'ログアウト' })).toBeVisible();
  });

  test('低いデスクトップ表示でも折りたたみサイドバーをスクロールできる', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 320 });
    await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });

    await page.route('**/api/auth/logout', ignoreRoute);
    await page.route('**/api/auth/guest', (route) => route.fulfill(json({ mode: 'guest' })));
    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [{ id: 'wp:guest:1', lemma: 'guest', sense_title: 'guest' }], total: 1 })),
    );

    await page.goto('/');
    await page.getByRole('button', { name: 'ゲスト閲覧モード' }).click();
    await page.getByRole('button', { name: 'サイドメニューを折りたたむ' }).click();
    await expect(page.getByRole('button', { name: 'サイドメニューを展開' })).toHaveAttribute('aria-expanded', 'false');

    const railScroll = await page.locator('.sidebar-main').evaluate((element) => {
      const sidebarMain = element as HTMLElement;
      sidebarMain.scrollTop = sidebarMain.scrollHeight;
      return {
        canScroll: sidebarMain.scrollHeight > sidebarMain.clientHeight,
        overflowY: getComputedStyle(sidebarMain).overflowY,
        scrollTop: sidebarMain.scrollTop,
      };
    });

    expect(railScroll.overflowY).toBe('auto');
    expect(railScroll.canScroll).toBe(true);
    expect(railScroll.scrollTop).toBeGreaterThan(0);

    await page.getByRole('button', { name: '設定' }).click();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
  });
});
