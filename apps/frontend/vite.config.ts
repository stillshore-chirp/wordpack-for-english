import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

const backendProxyTarget = process.env.BACKEND_PROXY_TARGET || "http://backend:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: backendProxyTarget,
        changeOrigin: true,
      },
    },
    hmr: {
      clientPort: 5173,
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // 新規メンバー向け: CIでのVitestカバレッジ閾値をここで集中管理する。
    // 段階的改善方針: functions は 66% → 70% → 75% → 80% と引き上げていく。
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'json-summary'],
      thresholds: {
        lines: 80,
        statements: 80,
        branches: 70,
        functions: 66, // 段階的改善: 現状66.37%から開始し、定期的に引き上げる
      },
    },
  },
});
