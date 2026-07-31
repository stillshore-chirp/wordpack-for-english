import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

describe('WordPackListPanel header layout', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    (globalThis as any).fetch = vi.fn();
    try {
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'tester', email: 'tester@example.com', display_name: 'Tester' },
        }),
      );
    } catch {
      // localStorage が使えない環境でもテストを継続する。
    }
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {
      // ignore
    }
  });

  const setupFetchMocks = () => {
    return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as URL).toString();
      const method = init?.method ?? 'GET';

      if (url.endsWith('/api/config') && method === 'GET') {
        return new Response(
          JSON.stringify({ request_timeout_ms: 60000, llm_model: 'gpt-5.6-luna' }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      if (url.startsWith('/api/word/packs?') && method === 'GET') {
        return new Response(
          JSON.stringify({
            items: [
              {
                id: 'wp:test:header',
                lemma: 'alpha',
                sense_title: 'Alpha overview',
                created_at: new Date().toISOString(),
                updated_at: new Date().toISOString(),
                is_empty: true,
                checked_only_count: 0,
                learned_count: 0,
              },
            ],
            total: 1,
            limit: 200,
            offset: 0,
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }

      return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
  };

  it('見出しと更新ボタンのDOM順が崩れない', async () => {
    setupFetchMocks();

    render(
      <AppProviders googleClientId="test-client">
        <App />
      </AppProviders>,
    );

    await waitFor(() => expect(screen.getByRole('heading', { name: /保存済みWordPack/ })).toBeInTheDocument());

    const heading = screen.getByRole('heading', { name: /保存済みWordPack/ });
    const refreshButton = screen.getByRole('button', { name: '更新' });
    const headerContainer = heading.parentElement;

    expect(headerContainer).not.toBeNull();
    expect(headerContainer).toContainElement(refreshButton);
    // モバイル時の縦配置でも、見出し→更新ボタンの順序が維持されることを保証する。
    expect(heading.compareDocumentPosition(refreshButton) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
