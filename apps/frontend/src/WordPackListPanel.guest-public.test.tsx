import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';

const renderWithAuth = () =>
  render(
    <AppProviders googleClientId="test-client">
      <App />
    </AppProviders>,
  );

const setupGuestPublicFetch = () => {
  const guestPublicRequests: Array<{ guest_public: boolean }> = [];
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input: any, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : (input as URL).toString();
    const method = init?.method ?? 'GET';

    if (url.endsWith('/api/config') && method === 'GET') {
      return new Response(
        JSON.stringify({ request_timeout_ms: 60000, llm_model: 'gpt-5.4-mini' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (url.startsWith('/api/word/packs?') && method === 'GET') {
      return new Response(
        JSON.stringify({
          items: [
            {
              id: 'wp:alpha',
              lemma: 'alpha',
              sense_title: 'Alpha overview',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              is_empty: false,
              checked_only_count: 0,
              learned_count: 0,
              guest_public: false,
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    if (url.endsWith('/api/word/packs/wp:alpha/guest-public') && method === 'POST') {
      const body = init?.body ? JSON.parse(init.body as string) : {};
      guestPublicRequests.push(body);
      return new Response(
        JSON.stringify({ word_pack_id: 'wp:alpha', guest_public: body.guest_public }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }

    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  });

  return { fetchMock, guestPublicRequests };
};

describe('WordPackListPanel guest public toggle', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try {
      localStorage.setItem(
        'wordpack.auth.v1',
        JSON.stringify({
          authMode: 'authenticated',
          user: { google_sub: 'sub', email: 'user@example.com', display_name: 'User' },
        }),
      );
    } catch {
      // localStorage が利用できない環境でもテストを継続する。
    }
  });

  afterEach(() => {
    try {
      localStorage.removeItem('wordpack.auth.v1');
    } catch {
      // ignore
    }
  });

  it('sends guest public update request when toggled', async () => {
    const { guestPublicRequests } = setupGuestPublicFetch();
    renderWithAuth();

    const user = userEvent.setup();
    await waitFor(() => expect(screen.getByRole('button', { name: 'alpha のその他の操作' })).toBeInTheDocument());

    await user.click(screen.getByRole('button', { name: 'alpha のその他の操作' }));
    await user.click(screen.getByRole('menuitem', { name: 'ゲスト公開にする' }));

    await waitFor(() => expect(guestPublicRequests).toHaveLength(1));
    expect(guestPublicRequests[0]).toEqual({ guest_public: true });
  });
});
