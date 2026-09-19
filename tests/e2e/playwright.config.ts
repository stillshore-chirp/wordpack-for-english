import crypto from 'node:crypto';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@playwright/test';

const currentDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(currentDir, '../..');
const baseURL = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173';
const e2eSessionSecretKey =
  (process.env.SESSION_SECRET_KEY || '').trim() || crypto.randomBytes(32).toString('hex');

export default defineConfig({
  testDir: currentDir,
  fullyParallel: true,
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  reporter: [
    ['list'],
    [
      'html',
      {
        open: 'never',
        outputFolder: path.join(repoRoot, 'playwright-report'),
      },
    ],
  ],
  outputDir: path.join(repoRoot, 'test-results'),
  use: {
    baseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: [
    {
      command:
        'python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --app-dir apps/backend',
      url: 'http://127.0.0.1:8000/healthz',
      reuseExistingServer: !process.env.CI,
      cwd: repoRoot,
      timeout: 120_000,
      env: {
        // Backend は起動時に SESSION_SECRET_KEY の厳格バリデーションを行う。
        // CI/E2E 実行では secrets を注入しないため、ここでテスト専用の安全な値を明示する。
        // - 32文字以上（backend の最小長制約）
        // - プレースホルダー禁止（"change-me" 等）
        // - 空文字が環境に設定されていても上書きする
        SESSION_SECRET_KEY: e2eSessionSecretKey,
        // E2E の実行時はローカル API を確実に参照させ、Vite のプロキシ先を固定する。
        BACKEND_PROXY_TARGET: 'http://127.0.0.1:8000',
        FIRESTORE_EMULATOR_HOST: process.env.FIRESTORE_EMULATOR_HOST ?? '127.0.0.1:8080',
        FIRESTORE_PROJECT_ID: process.env.FIRESTORE_PROJECT_ID ?? 'wordpack-ci',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: baseURL,
      reuseExistingServer: !process.env.CI,
      cwd: path.join(repoRoot, 'apps/frontend'),
      timeout: 120_000,
      env: {
        // E2EではGoogleログインの条件分岐を固定し、文言揺れを防ぐためのダミー値を設定する。
        VITE_GOOGLE_CLIENT_ID: 'e2e-dummy-client-id',
        // Viteプロセスにもローカルbackendを明示し、環境依存のDockerホスト名へフォールバックさせない。
        BACKEND_PROXY_TARGET: process.env.BACKEND_PROXY_TARGET || 'http://127.0.0.1:8000',
      },
    },
  ],
});
