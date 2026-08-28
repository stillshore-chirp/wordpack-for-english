import { expect, test } from '@playwright/test';

import { json, mockConfig, runA11yCheck, seedAuthenticatedSession } from './helpers';


test.describe('Quiz生成', () => {
  test('文対応の再試行状況と5回失敗理由を表示する', async ({ page, context }, testInfo) => {
    await seedAuthenticatedSession(context, page);
    await mockConfig(page, { requestTimeoutMs: 20000 });

    await page.route('**/api/word/packs?*', (route) => route.fulfill(json({
      items: [{
        id: 'wp:e2e:latency',
        lemma: 'latency',
        sense_title: '遅延',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
        is_empty: false,
        guest_public: false,
        examples_count: { Dev: 1, CS: 0, LLM: 0, Business: 0, Common: 0 },
        checked_only_count: 0,
        learned_count: 0,
      }],
      total: 1,
      limit: 100,
      offset: 0,
    })));
    await page.route('**/api/quiz?*', (route) => route.fulfill(json({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    })));
    await page.route('**/api/quiz/generate/jobs', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.fulfill(json({ detail: 'Not found' }, 404));
        return;
      }
      await route.fulfill(json({
        job_id: 'quiz-job:e2e-retry',
        status: 'queued',
        attempt_count: 0,
        attempt_limit: 5,
        retry_phase: null,
      }));
    });
    let statusReads = 0;
    await page.route('**/api/quiz/generate/jobs/quiz-job%3Ae2e-retry', async (route) => {
      statusReads += 1;
      if (statusReads === 1) {
        await route.fulfill(json({
          job_id: 'quiz-job:e2e-retry',
          status: 'running',
          attempt_count: 3,
          attempt_limit: 5,
          retry_phase: 'translation_alignment',
        }));
        return;
      }
      await route.fulfill(json({
        job_id: 'quiz-job:e2e-retry',
        status: 'failed',
        error_code: 'QUIZ_TRANSLATION_ALIGNMENT_FAILED',
        error: '英文と日本語訳の文対応を確認できなかったため、5回試行後にQuiz生成を停止しました。時間をおいてもう一度生成してください。',
        attempt_count: 5,
        attempt_limit: 5,
        retry_phase: 'translation_alignment',
      }));
    });

    await page.goto('/');
    await page.getByRole('button', { name: 'Quiz' }).click();
    await expect(page.getByRole('heading', { name: 'Quiz', exact: true })).toBeVisible();
    await page.getByLabel('含めるWordPack').selectOption('wp:e2e:latency');
    await page.getByRole('button', { name: '生成開始' }).click();

    await expect(page.getByRole('status')).toContainText('文対応を再確認しています（3/5）', {
      timeout: 10000,
    });
    await page.screenshot({ path: testInfo.outputPath('quiz-generation-retry-progress.png'), fullPage: true });
    await expect(page.getByRole('alert')).toContainText('5回試行後にQuiz生成を停止しました', {
      timeout: 10000,
    });
    await page.screenshot({ path: testInfo.outputPath('quiz-generation-alignment-failure.png'), fullPage: true });
    await expect(page.getByText('保存済みQuizはまだありません。')).toBeVisible();
    await runA11yCheck(page);
  });
});
