import { afterAll, afterEach, beforeAll, expect, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { setupServer } from 'msw/node';
import { toHaveNoViolations } from 'vitest-axe/dist/matchers';
import 'vitest-axe/extend-expect';

// 統合テストでは実HTTPを使うため、MSW のモック層を明示的に無効化する。
const isIntegrationTest = process.env.INTEGRATION_TEST === 'true';

// Ensure global fetch exists without external deps
if (!(globalThis as any).fetch) {
  (globalThis as any).fetch = ((): any => {
    throw new Error('global fetch is not available. Provide a mock in tests.');
  }) as any;
}

// Provide a robust matchMedia polyfill for jsdom environment used by Vitest
if (!(globalThis as any).window?.matchMedia) {
  const mm = (query: string) => {
    const listeners: Set<(e: MediaQueryListEvent) => void> = new Set();
    const mql: MediaQueryList = {
      media: query,
      matches: false,
      onchange: null,
      addListener: (cb: (e: MediaQueryListEvent) => void) => listeners.add(cb), // legacy API
      removeListener: (cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb), // legacy API
      addEventListener: (_type: 'change', cb: (e: MediaQueryListEvent) => void) => listeners.add(cb as any),
      removeEventListener: (_type: 'change', cb: (e: MediaQueryListEvent) => void) => listeners.delete(cb as any),
      dispatchEvent: (_ev: Event) => false,
    } as any;
    return mql;
  };
  (globalThis as any).window = (globalThis as any).window ?? (globalThis as any);
  (globalThis as any).window.matchMedia = mm as any;
}

// jsdomではNodeのプロセス共有BroadcastChannelが各テストwindowへ露出し、
// 独立したブラウザ環境を表すテストwindow間でlogout通知を誤共有する。
// BroadcastChannel専用テストは独立fakeを明示し、通常テストはstorage eventを使う。
if (
  typeof window !== 'undefined'
  && typeof window.BroadcastChannel === 'function'
  && window.BroadcastChannel === globalThis.BroadcastChannel
) {
  Object.defineProperty(window, 'BroadcastChannel', {
    configurable: true,
    writable: true,
    value: undefined,
  });
}

// a11y検査のために、axe の結果を直感的に読める matcher として拡張する。
expect.extend({ toHaveNoViolations });

// SettingsContext/AuthContext の初期同期に使う /api/config をテスト環境で安定供給する。
export const server = setupServer(
  http.get('/api/config', () => {
    return HttpResponse.json({ request_timeout_ms: 60000 });
  }),
);

beforeAll(() => {
  if (isIntegrationTest) return;
  server.listen({ onUnhandledRequest: 'warn' });
});

afterEach(() => {
  if (!isIntegrationTest) {
    server.resetHandlers();
  }
  vi.clearAllMocks();
});

afterAll(() => {
  if (isIntegrationTest) return;
  server.close();
});


