import { test, expect } from '@playwright/test';
import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';

type ExampleItem = { en: string; ja: string; grammar_ja?: string };

type Examples = {
  Dev: ExampleItem[];
  CS: ExampleItem[];
  LLM: ExampleItem[];
  Business: ExampleItem[];
  Common: ExampleItem[];
};

type WordPack = {
  lemma: string;
  sense_title: string;
  pronunciation: {
    ipa_GA: string | null;
    ipa_RP: string | null;
    syllables: string | null;
    stress_index: number | null;
    linking_notes: string[];
  };
  senses: Array<{ id: string; gloss_ja: string; definition_ja: string; nuances_ja: string; patterns: string[]; synonyms: string[]; antonyms: string[]; register: string; notes_ja: string }>;
  collocations: {
    general: { verb_object: string[]; adj_noun: string[]; prep_noun: string[] };
    academic: { verb_object: string[]; adj_noun: string[]; prep_noun: string[] };
  };
  contrast: string[];
  examples: Examples;
  etymology: { note: string; confidence: string };
  study_card: string;
  citations: Array<{ text: string }>;
  confidence: string;
};

const DEFAULT_E2E_ACTION_THRESHOLD_MS = 15000;

// CI/ローカル差分によるフレークを避けるため、環境変数で閾値を調整できるようにする。
const getE2eActionThresholdMs = (): number => {
  const rawValue = process.env.E2E_ACTION_THRESHOLD_MS;
  const parsedValue = rawValue ? Number(rawValue) : DEFAULT_E2E_ACTION_THRESHOLD_MS;
  if (!Number.isFinite(parsedValue) || parsedValue <= 0) {
    return DEFAULT_E2E_ACTION_THRESHOLD_MS;
  }
  return parsedValue;
};

// 主要操作の計測結果を CI で集計しやすくするために、最小限の統計情報を出す。
const summarizeDurations = (durations: number[]) => {
  const count = durations.length;
  if (count === 0) {
    return { count: 0, averageMs: 0, maxMs: 0 };
  }
  const total = durations.reduce((acc, value) => acc + value, 0);
  return {
    count,
    averageMs: total / count,
    maxMs: Math.max(...durations),
  };
};

const createBaseWordPack = (lemma: string): WordPack => ({
  lemma,
  sense_title: `${lemma} 概説`,
  pronunciation: {
    ipa_GA: null,
    ipa_RP: null,
    syllables: null,
    stress_index: null,
    linking_notes: [],
  },
  senses: [
    {
      id: 's1',
      gloss_ja: '意味',
      definition_ja: '定義',
      nuances_ja: 'ニュアンス',
      patterns: ['p1'],
      synonyms: ['syn'],
      antonyms: ['ant'],
      register: 'formal',
      notes_ja: '注意',
    },
  ],
  collocations: {
    general: { verb_object: [], adj_noun: [], prep_noun: [] },
    academic: { verb_object: [], adj_noun: [], prep_noun: [] },
  },
  contrast: [],
  examples: {
    Dev: [
      {
        en: `${lemma} dev example starts. ${lemma} dev example continues.`,
        ja: `${lemma} の例文が始まります。${lemma} の例文が続きます。`,
        grammar_ja: '第3文型',
      },
    ],
    CS: [],
    LLM: [],
    Business: [],
    Common: [],
  },
  etymology: { note: '-', confidence: 'low' },
  study_card: `${lemma} study`,
  citations: [],
  confidence: 'medium',
});

const cloneWordPack = (wordPack: WordPack): WordPack => JSON.parse(JSON.stringify(wordPack));

// 例文の追加・削除・再生成を1テスト内で完結させるため、
// メモリ内ストアで WordPack データを更新する。
const createWordPackStore = () => {
  const wordPackId = 'wp:e2e:001';
  let currentWordPack: WordPack | null = null;

  const create = (lemma: string) => {
    currentWordPack = createBaseWordPack(lemma);
    return wordPackId;
  };

  const read = () => (currentWordPack ? cloneWordPack(currentWordPack) : null);

  const addExamples = (category: keyof Examples) => {
    if (!currentWordPack) return;
    const next = currentWordPack.examples[category];
    next.push(
      { en: `${currentWordPack.lemma} extra example 1`, ja: '追加例文1' },
      { en: `${currentWordPack.lemma} extra example 2`, ja: '追加例文2' },
    );
  };

  const deleteExample = (category: keyof Examples, index: number) => {
    if (!currentWordPack) return;
    currentWordPack.examples[category].splice(index, 1);
  };

  const regenerate = () => {
    if (!currentWordPack) return null;
    currentWordPack = {
      ...currentWordPack,
      sense_title: `${currentWordPack.lemma} 再生成済み`,
    };
    return cloneWordPack(currentWordPack);
  };

  const reset = () => {
    currentWordPack = null;
  };

  return {
    wordPackId,
    create,
    read,
    addExamples,
    deleteExample,
    regenerate,
    reset,
  };
};

const toWordPackListItem = (id: string, wordPack: WordPack) => {
  const examplesCount = {
    Dev: wordPack.examples.Dev.length,
    CS: wordPack.examples.CS.length,
    LLM: wordPack.examples.LLM.length,
    Business: wordPack.examples.Business.length,
    Common: wordPack.examples.Common.length,
  };
  return {
    id,
    lemma: wordPack.lemma,
    sense_title: wordPack.sense_title,
    created_at: '2026-06-06T00:00:00.000Z',
    updated_at: '2026-06-06T00:00:00.000Z',
    is_empty: false,
    examples_count: examplesCount,
    checked_only_count: 0,
    learned_count: 0,
    guest_public: false,
  };
};

test.describe('WordPack 操作', () => {
  test('入力エラーのヘルプは入力欄の列で読める', async ({ page, context }) => {
    await page.setViewportSize({ width: 430, height: 640 });
    await seedAuthenticatedSession(context, page);
    await mockConfig(page, { requestTimeoutMs: 20000 });

    await page.route('**/api/word/packs?*', (route) =>
      route.fulfill(json({ items: [], total: 0, limit: 200, offset: 0 })),
    );

    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const input = page.getByLabel('見出し語');
    await input.fill('日本語');

    const helper = page.locator('#wordpack-lemma-help');
    await expect(input).toHaveAttribute('aria-describedby', 'wordpack-lemma-help');
    await expect(input).toHaveAttribute('aria-invalid', 'true');
    await expect(helper).toContainText('英数字と半角スペース、ハイフン、アポストロフィのみ利用できます');

    const metrics = await page.evaluate(() => {
      const inputEl = document.querySelector<HTMLElement>('#wordpack-lemma-input');
      const helperEl = document.querySelector<HTMLElement>('#wordpack-lemma-help');
      if (!inputEl || !helperEl) {
        throw new Error('lemma input or helper is missing');
      }
      const inputRect = inputEl.getBoundingClientRect();
      const helperRect = helperEl.getBoundingClientRect();
      const helperStyle = window.getComputedStyle(helperEl);
      return {
        inputLeft: inputRect.left,
        inputWidth: inputRect.width,
        helperLeft: helperRect.left,
        helperWidth: helperRect.width,
        gridColumnStart: helperStyle.gridColumnStart,
        gridColumnEnd: helperStyle.gridColumnEnd,
      };
    });

    expect(metrics.gridColumnStart).toBe('2');
    expect(metrics.gridColumnEnd).toBe('-1');
    expect(metrics.helperLeft).toBeGreaterThanOrEqual(metrics.inputLeft - 1);
    expect(metrics.helperWidth).toBeGreaterThan(metrics.inputWidth * 0.85);
    await runA11yCheck(page);
  });

  test('例文の追加/削除/再生成を1本のシナリオで完結できる', async ({ page, context }) => {
    const store = createWordPackStore();
    const actionDurationsMs: number[] = [];
    const actionThresholdMs = getE2eActionThresholdMs();

    await seedAuthenticatedSession(context, page);
    await mockConfig(page, { requestTimeoutMs: 20000 });

    await page.route('**/api/word/packs?*', (route) => {
      const payload = store.read();
      const items = payload ? [toWordPackListItem(store.wordPackId, payload)] : [];
      return route.fulfill(json({ items, total: items.length, limit: 200, offset: 0 }));
    });

    await page.route('**/api/word/packs', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fulfill(json({ detail: 'Not found' }, 404));
        return;
      }
      const body = route.request().postDataJSON() as { lemma?: string } | null;
      const id = store.create(body?.lemma ?? 'alpha');
      await route.fulfill(json({ id }));
    });

    await page.route('**/api/word/packs/**', async (route) => {
      const url = route.request().url();
      const method = route.request().method();

      if (url.includes('/examples/') && method === 'POST') {
        const match = url.match(/examples\/([^/]+)\/generate/);
        const category = (match?.[1] ?? 'Dev') as keyof Examples;
        store.addExamples(category);
        await route.fulfill(json({ ok: true }));
        return;
      }

      if (url.includes('/examples/') && method === 'DELETE') {
        const match = url.match(/examples\/([^/]+)\/(\d+)/);
        const category = (match?.[1] ?? 'Dev') as keyof Examples;
        const index = Number(match?.[2] ?? 0);
        store.deleteExample(category, index);
        await route.fulfill(json({ ok: true }));
        return;
      }

      if (url.endsWith('/regenerate/async') && method === 'POST') {
        await route.fulfill(json({ job_id: 'job:e2e:1', status: 'running' }));
        return;
      }

      if (url.includes('/regenerate/jobs/') && method === 'GET') {
        const result = store.regenerate();
        await route.fulfill(json({ job_id: 'job:e2e:1', status: 'succeeded', result }));
        return;
      }

      if (method === 'GET') {
        const payload = store.read();
        await route.fulfill(payload ? json(payload) : json({ detail: 'Not found' }, 404));
        return;
      }

      await route.fulfill(json({ detail: 'Not found' }, 404));
    });

    await test.step('Given: WordPack を作成して編集可能な状態にする', async () => {
      await page.goto('/');
      await page.waitForLoadState('networkidle');
      await expect(page.getByRole('heading', { name: 'WordPack', level: 1 })).toBeVisible();
      await runA11yCheck(page);
      // WordPack の入力・作成ボタンは Lexicon 右側の作成パネルに配置されている。
      await page.getByLabel('見出し語').fill('alpha');
      // 入力バリデーション完了後にボタンが有効化されるため、明示的に待機してから押下する。
      const generateButton = page.getByRole('button', { name: '作成を開始' });
      const createWordPackButton = page.getByRole('button', { name: 'WordPackのみ作成' });
      await expect(createWordPackButton).toBeEnabled();
      await page.getByLabel('見出し語').focus();
      await page.keyboard.press('Tab');
      // タブ順は「生成」→「WordPackのみ作成」の順に並ぶため、2回で作成ボタンへ到達する。
      await expect(generateButton).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(createWordPackButton).toBeFocused();
      const actionStartTime = await page.evaluate(() => {
        performance.clearMarks('wordpack-generate-start');
        performance.clearMarks('wordpack-generate-end');
        performance.clearMeasures('wordpack-generate');
        performance.mark('wordpack-generate-start');
        return performance.now();
      });
      await page.keyboard.press('Space');
      const alphaCard = page.getByTestId('wp-card').filter({ hasText: 'alpha' }).first();
      await expect(alphaCard).toBeVisible();
      await alphaCard.getByRole('button', { name: '開く' }).click();
      await expect(page.getByRole('dialog', { name: /WordPack プレビュー/ })).toBeVisible();
      await expect(page.getByRole('heading', { name: /例文/ })).toBeVisible();
      const englishExampleSentence = page.locator('.ex-en .sentence-pair-highlight').first();
      const japaneseExampleSentence = page.getByRole('group', { name: '日本語訳 1: 英文と対応' }).first();
      await englishExampleSentence.hover();
      await expect(englishExampleSentence).toHaveClass(/is-active/);
      await expect(japaneseExampleSentence).toHaveClass(/is-active/);
      await japaneseExampleSentence.click();
      await expect(englishExampleSentence).toHaveClass(/is-pinned/);
      await expect(japaneseExampleSentence).toHaveClass(/is-pinned/);
      const actionEnd = await page.evaluate(() => {
        performance.mark('wordpack-generate-end');
        const measure = performance.measure(
          'wordpack-generate',
          'wordpack-generate-start',
          'wordpack-generate-end',
        );
        const endTime = performance.now();
        const measureEntry = performance.getEntriesByName('wordpack-generate').pop();
        const durationMs = measureEntry?.duration ?? measure.duration;
        performance.clearMarks('wordpack-generate-start');
        performance.clearMarks('wordpack-generate-end');
        performance.clearMeasures('wordpack-generate');
        return { endTime, durationMs };
      });
      const actionDurationMs = actionEnd.endTime - actionStartTime;
      const measureDurationMs = actionEnd.durationMs;
      actionDurationsMs.push(actionDurationMs);
      expect(actionDurationMs).toBeLessThan(actionThresholdMs);
      const stats = summarizeDurations(actionDurationsMs);
      // CI で機械的に集計できるよう、JSON 形式でログを出力する。
      console.info(
        '[e2e-metric]',
        JSON.stringify({
          event: 'wordpack_generate_render_time',
          count: stats.count,
          average_ms: Number(stats.averageMs.toFixed(2)),
          max_ms: Number(stats.maxMs.toFixed(2)),
          measure_ms: Number(measureDurationMs.toFixed(2)),
          threshold_ms: actionThresholdMs,
        }),
      );
    });

    await test.step('When: 例文を追加生成する', async () => {
      await page.getByRole('button', { name: 'Dev例文を2件追加生成' }).click();
    });

    await test.step('Then: 例文の件数が増えている', async () => {
      await expect(page.getByText('Dev (3件)')).toBeVisible();
      await page.getByRole('button', { name: 'WordPackプレビューを閉じる' }).click();
      const queue = page.getByRole('region', { name: '生成キュー' });
      await expect(queue).toContainText('alpha');
      await expect(queue).toContainText('Dev: gpt-5.4-mini');
      const alphaCard = page.getByTestId('wp-card').filter({ hasText: 'alpha' }).first();
      await alphaCard.getByRole('button', { name: '開く' }).click();
      await expect(page.getByRole('dialog', { name: /WordPack プレビュー/ })).toBeVisible();
    });

    await test.step('When: 追加した例文を削除する', async () => {
      await page.getByRole('button', { name: 'alphaのDev例文1を削除' }).click();
      await page.getByRole('button', { name: '削除する' }).click();
      // 削除完了は件数の変化で観測する（通知UIは他のトーストと競合しやすい）。
    });

    await test.step('Then: 例文の件数が減っている', async () => {
      await expect(page.getByText('Dev (2件)')).toBeVisible();
    });

    await test.step('When: WordPack を再生成する', async () => {
      await page.getByRole('button', { name: '再生成' }).click();
    });

    await test.step('Then: 再生成完了メッセージが出る', async () => {
      await expect(page.getByText('alpha 再生成済み')).toBeVisible();
      await page.getByRole('button', { name: 'WordPackプレビューを閉じる' }).click();
      const queue = page.getByRole('region', { name: '生成キュー' });
      await expect(queue).toContainText('alpha');
      await expect(queue).toContainText('完了3');
      const alphaCard = page.getByTestId('wp-card').filter({ hasText: 'alpha' }).first();
      await alphaCard.getByRole('button', { name: '開く' }).click();
      await expect(page.getByRole('dialog', { name: /WordPack プレビュー/ })).toBeVisible();
    });

    await test.step('Then: テストデータを後片付けする', async () => {
      store.reset();
      await expect(page.getByRole('heading', { name: /例文/ })).toBeVisible();
    });
  });
});
