import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from './App';
import { AppProviders } from './main';
import { guestLockMessage } from './components/GuestLock';

const renderWithGuestSession = () =>
  render(
    <AppProviders googleClientId="test-client">
      <App />
    </AppProviders>,
  );

// ゲストのUI制御を観察するため、最小の WordPack レスポンスを固定化する。
const setupGuestWordPackFetch = () => {
  (globalThis as any).fetch = vi.fn();
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
              id: 'wp:guest:alpha',
              lemma: 'alpha',
              sense_title: 'Alpha overview',
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              is_empty: true,
              checked_only_count: 0,
              learned_count: 0,
              guest_public: true,
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

  return fetchMock;
};

describe('WordPackListPanel guest controls', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setupGuestWordPackFetch();
    try {
      localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
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

  it('disables write actions and shows the guest tooltip on hover', async () => {
    renderWithGuestSession();

    const user = userEvent.setup();

    // WordPack一覧がロードされて生成ボタンが表示されるまで待機
    await waitFor(
      () => expect(screen.getByRole('button', { name: '生成' })).toBeInTheDocument(),
      { timeout: 5000 },
    );

    expect(screen.queryByRole('group', { name: 'WordPack選択操作' })).not.toBeInTheDocument();
    const generateButton = screen.getByRole('button', { name: '生成' });

    expect(generateButton).toBeDisabled();

    await act(async () => {
      await user.click(screen.getByRole('button', { name: 'alpha のその他の操作' }));
    });
    const cardDeleteButton = screen.getByRole('menuitem', { name: '削除' });
    expect(cardDeleteButton).toBeDisabled();

    const checkbox = screen.getByRole('checkbox', { name: 'WordPack alpha を選択' });
    await act(async () => {
      await user.click(checkbox);
    });

    const selectionBar = screen.getByRole('group', { name: 'WordPack選択操作' });
    const bulkDeleteButton = within(selectionBar).getByRole('button', { name: '削除' });
    expect(bulkDeleteButton).toBeDisabled();

    vi.useFakeTimers();

    const wrapper = bulkDeleteButton.parentElement as HTMLElement;
    act(() => {
      fireEvent.mouseEnter(wrapper);
    });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getByRole('tooltip')).toHaveTextContent(guestLockMessage);

    act(() => {
      fireEvent.mouseLeave(wrapper);
    });
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();

    vi.useRealTimers();
  });
});
