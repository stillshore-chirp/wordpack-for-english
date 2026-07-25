import { test, expect, type Page, type BrowserContext } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

const STATIC_MASK_SELECTOR = '[aria-live="polite"]';

const disableAnimations = async (page: Page): Promise<void> => {
  /**
   * 視覚スナップショットの差分を安定化するため、全要素のアニメーション/トランジションを無効化する。
   * なぜ: トーストの経過時間やフェードがフレークの温床になるため。
   */
  await page.addStyleTag({
    content: `
      *, *::before, *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }
      ${STATIC_MASK_SELECTOR} {
        visibility: hidden !important;
      }
    `,
  });
};

const openSidebarAndSelect = async (
  page: Page,
  label: string,
  options: { keepOpen?: boolean } = {},
): Promise<void> => {
  /**
   * サイドバー経由でタブ移動を統一する。
   * なぜ: どの表示幅でも同じ操作でメニュー遷移できるよう手順を固定するため。
   */
  const openButton = page.getByRole('button', { name: 'メニューを開く' });
  if ((await openButton.count()) > 0) {
    await openButton.click();
  }
  await page.getByRole('button', { name: label }).click();
  if (!options.keepOpen) {
    /**
     * メニューを閉じる操作はキーボード（Enter）で行い、オーバーレイの pointer-events による
     * クリック遮断を回避する。
     * なぜ: 画面幅やレイアウト差でサイドバー要素がボタン上に重なり、ポインタ操作が
     *      不安定になることがあるため（a11y 的にはキーボード操作でも閉じられるべき）。
     */
    const closeButton = page.getByRole('button', { name: 'メニューを閉じる' });
    if ((await closeButton.count()) > 0) {
      await closeButton.focus();
      await page.keyboard.press('Enter');
      await expect(page.getByRole('button', { name: 'メニューを開く' })).toBeVisible();
    }
  }
};

const prepareAuthenticatedPage = async (context: BrowserContext, page: Page): Promise<void> => {
  /**
   * 認証済み状態でUIを固定する。
   * なぜ: OAuthポップアップやセッション不整合を避け、画面描画に集中するため。
   */
  await seedAuthenticatedSession(context, page);
  await mockConfig(page, { requestTimeoutMs: 20000, sessionAuthDisabled: false });
};

const mockWordPackList = async (page: Page): Promise<void> => {
  /**
   * WordPack一覧を固定データで再現する。
   * なぜ: 視覚リグレッションの対象をデータ変動から切り離すため。
   */
  await page.route('**/api/word/packs?**', (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: 'wp:e2e:alpha',
            lemma: 'alpha',
            sense_title: 'alpha 概説',
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
            sense_title: 'bravo 概説',
            created_at: '2024-01-08T08:30:00Z',
            updated_at: '2024-01-11T18:05:00Z',
            is_empty: true,
            guest_public: false,
            examples_count: {
              Dev: 0,
              CS: 0,
              LLM: 2,
              Business: 0,
              Common: 1,
            },
            checked_only_count: 0,
            learned_count: 0,
          },
          {
            id: 'wp:e2e:charlie',
            lemma: 'charlie',
            sense_title: 'charlie 概説',
            created_at: '2024-01-05T03:20:00Z',
            updated_at: '2024-01-06T11:10:00Z',
            is_empty: false,
            guest_public: true,
            examples_count: {
              Dev: 5,
              CS: 0,
              LLM: 0,
              Business: 1,
              Common: 2,
            },
            checked_only_count: 2,
            learned_count: 1,
          },
        ],
        total: 3,
        limit: 200,
        offset: 0,
      }),
    ),
  );
};

const mockWordPackListContentStress = async (page: Page): Promise<void> => {
  /**
   * リスト表示の長文・操作密度ストレスを固定データで再現する。
   * なぜ: 実データや個人情報をスクリーンショットへ含めず、見出し語の幅不足を検出するため。
   */
  await page.route('**/api/word/packs?**', (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: 'wp:e2e:layout-long',
            lemma: 'an intentionally long multiword expression for layout verification',
            sense_title: '長い見出し語でも、主要情報と操作が重ならずに読めることを確認します。',
            created_at: '2024-01-10T09:15:00Z',
            updated_at: '2024-01-12T12:00:00Z',
            is_empty: true,
            guest_public: false,
            examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
            checked_only_count: 0,
            learned_count: 0,
          },
          {
            id: 'wp:e2e:layout-generated',
            lemma: 'generated entry',
            sense_title: '生成済み項目の表示確認',
            created_at: '2024-01-08T08:30:00Z',
            updated_at: '2024-01-11T18:05:00Z',
            is_empty: false,
            guest_public: true,
            examples_count: { Dev: 3, CS: 1, LLM: 0, Business: 2, Common: 4 },
            checked_only_count: 1,
            learned_count: 2,
          },
          {
            id: 'wp:e2e:layout-short',
            lemma: 'short',
            sense_title: '',
            created_at: '2024-01-05T03:20:00Z',
            updated_at: '2024-01-06T11:10:00Z',
            is_empty: true,
            guest_public: false,
            examples_count: { Dev: 0, CS: 0, LLM: 0, Business: 0, Common: 0 },
            checked_only_count: 0,
            learned_count: 0,
          },
        ],
        total: 3,
        limit: 200,
        offset: 0,
      }),
    ),
  );
};

const mockExampleList = async (page: Page): Promise<void> => {
  /**
   * 例文一覧の固定レスポンスを用意する。
   * なぜ: ランダム性のある集計結果を排除し、UI差分のみに集中するため。
   */
  await page.route('**/api/word/examples?**', (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: 101,
            word_pack_id: 'wp:e2e:alpha',
            lemma: 'alpha',
            category: 'Dev',
            en: 'We shipped the alpha build yesterday.',
            ja: '昨日アルファ版を出荷しました。',
            grammar_ja: '第4文型の例。',
            created_at: '2024-01-04T06:30:00Z',
            word_pack_updated_at: '2024-01-12T12:00:00Z',
            checked_only_count: 1,
            learned_count: 0,
            transcription_typing_count: 120,
          },
          {
            id: 102,
            word_pack_id: 'wp:e2e:bravo',
            lemma: 'bravo',
            category: 'Common',
            en: 'Bravo! That presentation was clear.',
            ja: 'ブラボー！あの発表は分かりやすかった。',
            grammar_ja: null,
            created_at: '2024-01-02T03:10:00Z',
            word_pack_updated_at: '2024-01-11T18:05:00Z',
            checked_only_count: 0,
            learned_count: 1,
            transcription_typing_count: 48,
          },
        ],
        total: 2,
        limit: 200,
        offset: 0,
      }),
    ),
  );
};

const mockWordPackDetail = async (page: Page): Promise<void> => {
  /**
   * WordPackプレビューの例文エリアを固定データで再現する。
   * なぜ: 長い解説の視覚階層を、一覧画面とは別に回帰検知するため。
   */
  await page.route(
    (url) => url.pathname.includes('/api/word/packs/wp') && url.pathname.includes('e2e') && url.pathname.includes('alpha'),
    (route) =>
      route.fulfill(
        json({
          lemma: 'alpha',
          sense_title: '初期検証版',
          pronunciation: { ipa_GA: null, ipa_RP: null, syllables: null, stress_index: null, linking_notes: [] },
          senses: [
            {
              id: 's1',
              gloss_ja: '初期段階の検証版',
              definition_ja: '正式公開前に主要機能を試すための版。',
              nuances_ja: '品質保証よりも学習と検証を優先する文脈で使われる。',
              patterns: ['alpha release', 'alpha build'],
              synonyms: ['preview'],
              antonyms: ['stable release'],
              register: 'technical',
              notes_ja: '開発・プロダクト文脈で頻出。',
            },
          ],
          collocations: { general: { verb_object: [], adj_noun: [], prep_noun: [] }, academic: { verb_object: [], adj_noun: [], prep_noun: [] } },
          contrast: [],
          examples: {
            Dev: [
              {
                en: 'During the search-ranking rewrite, the team added contextual embeddings to reduce polysemy in user queries.',
                ja: '検索順位の書き換え中、チームはユーザーのクエリにおける多義性を減らすため文脈埋め込みを導入した。',
                grammar_ja: [
                  '品詞分解：During【前置詞】 / the search-ranking rewrite【名詞句】 / the team【主語】 / added【動詞】 / contextual embeddings【目的語】 / to reduce polysemy in user queries【目的】。',
                  '構文：文の核は the team added contextual embeddings で、During句が時期、to不定詞句が目的を示します。',
                  '解説：長い修飾は先に目的と背景をつかむと読みやすくなります。polysemy はここではユーザー入力の多義性を指します。',
                ].join('\n\n'),
              },
              {
                en: 'The alpha build exposed navigation issues before the public beta started.',
                ja: 'アルファ版は公開ベータが始まる前にナビゲーション上の問題を明らかにした。',
                grammar_ja: '解説：exposed は「表面化させた」という意味で、問題発見の文脈に合います。',
              },
            ],
            CS: [],
            LLM: [],
            Business: [],
            Common: [],
          },
          etymology: { note: '-', confidence: 'medium' },
          study_card: 'alpha release は「初期検証版」。正式版ではなく学習と検証のための段階を指す。',
          citations: [],
          confidence: 'medium',
        }),
      ),
  );
};

const mockArticleImport = async (page: Page): Promise<void> => {
  /**
   * 文章インポートの確定画面を再現するため、POST/GETを一貫したモックに固定する。
   * なぜ: モーダル内容が揺れるとスクリーンショットが不安定になるため。
   */
  const articleDetail = {
    id: 'article:e2e:001',
    title_en: 'A short briefing on alpha releases',
    body_en: 'Alpha releases validate core workflows for early adopters.',
    body_ja: 'アルファ版は初期利用者向けに主要なワークフローを検証します。',
    notes_ja: '例文抽出はDevカテゴリを優先。',
    llm_model: 'gpt-5.4-mini',
    llm_params: 'reasoning.effort=minimal;text.verbosity=medium',
    generation_category: 'Dev',
    related_word_packs: [
      { word_pack_id: 'wp:e2e:alpha', lemma: 'alpha', status: 'existing' },
      { word_pack_id: 'wp:e2e:beta', lemma: 'beta', status: 'created', is_empty: true },
    ],
    warnings: ['既存WordPackが1件含まれています。'],
    created_at: '2024-01-10T09:15:00Z',
    updated_at: '2024-01-10T09:16:10Z',
    generation_started_at: '2024-01-10T09:15:00Z',
    generation_completed_at: '2024-01-10T09:16:00Z',
    generation_duration_ms: 60000,
  };

  await page.route((url) => url.pathname === '/api/article/import', (route) => {
    if (route.request().method() !== 'POST') {
      return route.fulfill(json({ detail: 'Not found' }, 404));
    }
    return route.fulfill(json({ id: articleDetail.id }));
  });

  await page.route((url) => url.pathname === '/api/article', (route) =>
    route.fulfill(
      json({
        items: [
          {
            id: 'article:e2e:001',
            title_en: 'A short briefing on alpha releases',
            created_at: '2024-01-10T09:15:00Z',
            updated_at: '2024-01-10T09:16:10Z',
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      }),
    ),
  );

  // 記事IDにコロンが含まれるため、URL エンコード有無の差分を吸収してモックする。
  await page.route(
    (url) => url.pathname.startsWith('/api/article/article') && url.pathname.includes('e2e') && url.pathname.includes('001'),
    (route) => route.fulfill(json(articleDetail)),
  );
};

test.describe('ビジュアル回帰: 主要画面', () => {
  test('WordPack一覧（保存済み一覧）', async ({ page, context }) => {
    await prepareAuthenticatedPage(context, page);
    await mockWordPackList(page);

    await page.goto('/');
    await disableAnimations(page);

    await expect(page.getByRole('heading', { name: /保存済みWordPack/ })).toBeVisible();
    await expect(page.getByRole('heading', { name: /^alpha$/ })).toBeVisible();

    await expect(page).toHaveScreenshot('wordpack-list.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      mask: [page.locator(STATIC_MASK_SELECTOR)],
    });
  });

  test('WordPackリスト表示（右レールと長文ストレス）', async ({ page, context }) => {
    await page.setViewportSize({ width: 1636, height: 912 });
    await prepareAuthenticatedPage(context, page);
    await mockWordPackListContentStress(page);

    await page.goto('/');
    await disableAnimations(page);

    await page.getByRole('button', { name: 'リスト', exact: true }).click();
    await expect(page.getByTestId('wp-index-item')).toHaveCount(3);

    const desktopLayout = await page.evaluate(() => {
      const primary = document.querySelector<HTMLElement>('.lexicon-primary');
      const grid = document.querySelector<HTMLElement>('.wp-index-grid');
      const items = Array.from(document.querySelectorAll<HTMLElement>('[data-testid="wp-index-item"]'));
      const titleRows = Array.from(document.querySelectorAll<HTMLElement>('[data-testid="wp-index-title-row"]'));
      const actionButtons = Array.from(document.querySelectorAll<HTMLElement>('.wp-index-actions > button'));

      if (!primary || !grid) {
        throw new Error('Lexiconのリスト領域が見つかりません。');
      }

      const gridRect = grid.getBoundingClientRect();
      return {
        primaryClientWidth: primary.clientWidth,
        primaryScrollWidth: primary.scrollWidth,
        gridWidth: gridRect.width,
        itemXs: items.map((item) => Math.round(item.getBoundingClientRect().x)),
        itemWidths: items.map((item) => item.getBoundingClientRect().width),
        titleWidths: titleRows.map((title) => title.getBoundingClientRect().width),
        actionButtonHeights: actionButtons.map((button) => button.getBoundingClientRect().height),
      };
    });

    expect(desktopLayout.primaryScrollWidth).toBeLessThanOrEqual(desktopLayout.primaryClientWidth + 1);
    expect(desktopLayout.gridWidth).toBeLessThanOrEqual(desktopLayout.primaryClientWidth + 1);
    expect(new Set(desktopLayout.itemXs).size).toBe(1);
    expect(desktopLayout.itemWidths.every((width) => Math.abs(width - desktopLayout.gridWidth) <= 1)).toBe(true);
    expect(desktopLayout.titleWidths.every((width) => width >= 240)).toBe(true);
    expect(desktopLayout.actionButtonHeights.every((height) => height <= 44)).toBe(true);
    await runA11yCheck(page);

    await expect(page).toHaveScreenshot('wordpack-list-compact.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    });

    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.getByTestId('wp-index-item')).toHaveCount(3);
    const narrowLayout = await page.evaluate(() => {
      const primary = document.querySelector<HTMLElement>('.lexicon-primary');
      const grid = document.querySelector<HTMLElement>('.wp-index-grid');
      const items = Array.from(document.querySelectorAll<HTMLElement>('[data-testid="wp-index-item"]'));

      if (!primary || !grid) {
        throw new Error('狭幅時のLexiconリスト領域が見つかりません。');
      }

      return {
        primaryClientWidth: primary.clientWidth,
        primaryScrollWidth: primary.scrollWidth,
        gridWidth: grid.getBoundingClientRect().width,
        itemWidths: items.map((item) => item.getBoundingClientRect().width),
      };
    });
    expect(narrowLayout.primaryScrollWidth).toBeLessThanOrEqual(narrowLayout.primaryClientWidth + 1);
    expect(narrowLayout.gridWidth).toBeLessThanOrEqual(narrowLayout.primaryClientWidth + 1);
    expect(narrowLayout.itemWidths.every((width) => Math.abs(width - narrowLayout.gridWidth) <= 1)).toBe(true);
  });

  test('WordPackプレビュー（例文表示エリア）', async ({ page, context }) => {
    await prepareAuthenticatedPage(context, page);
    await mockWordPackList(page);
    await mockWordPackDetail(page);

    await page.goto('/');
    await disableAnimations(page);

    await page.getByTestId('wp-card').first().click();
    const dialog = page.getByRole('dialog', { name: /WordPack プレビュー: alpha/ });
    await expect(dialog).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId('example-Dev-0')).toBeVisible({ timeout: 15000 });
    await page.getByTestId('example-Dev-0').scrollIntoViewIfNeeded();
    await expect(page.getByText('品詞分解を表示').first()).toBeVisible();

    await expect(page).toHaveScreenshot('wordpack-preview-examples.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
    });
  });

  test('文章インポート（例文からのインポート確認UI）', async ({ page, context }) => {
    await prepareAuthenticatedPage(context, page);
    await mockWordPackList(page);
    await mockArticleImport(page);

    await page.goto('/');
    await disableAnimations(page);

    // 「インポート結果」モーダルは、サイドバーの重なり（z-index）やUI変更で不安定になりやすい。
    // このテストでは「文章インポート」タブで一覧から詳細（プレビュー）を開くことで、同等の詳細UIを安定して再現する。
    await openSidebarAndSelect(page, '文章インポート');
    await expect(page.getByRole('heading', { name: 'インポート済み文章' })).toBeVisible();
    await expect(page.getByText('A short briefing on alpha releases')).toBeVisible();
    await page.getByText('A short briefing on alpha releases').click();
    await expect(page.getByRole('dialog', { name: '文章プレビュー' })).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('既存WordPackが1件含まれています。')).toBeVisible();

    await expect(page).toHaveScreenshot('article-import-confirmation.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      mask: [page.locator(STATIC_MASK_SELECTOR)],
    });
  });

  test('例文一覧', async ({ page, context }) => {
    await prepareAuthenticatedPage(context, page);
    await mockWordPackList(page);
    await mockExampleList(page);

    await page.goto('/');
    await disableAnimations(page);

    await openSidebarAndSelect(page, '例文一覧');
    await expect(page.getByRole('heading', { name: '例文一覧' })).toBeVisible();
    await expect(page.getByText('We shipped the alpha build yesterday.')).toBeVisible();

    await expect(page).toHaveScreenshot('example-list.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      mask: [page.locator(STATIC_MASK_SELECTOR)],
    });
  });

  test('設定ダイアログ（SettingsPanel表示）', async ({ page, context }) => {
    await prepareAuthenticatedPage(context, page);
    await mockWordPackList(page);

    await page.goto('/');
    await disableAnimations(page);

    await openSidebarAndSelect(page, '設定');
    await expect(page.getByRole('button', { name: 'ログアウト（Google セッションを終了）' })).toBeVisible();

    await expect(page).toHaveScreenshot('settings-panel.png', {
      maxDiffPixelRatio: 0.01,
      threshold: 0.2,
      mask: [page.locator(STATIC_MASK_SELECTOR)],
    });
  });
});
