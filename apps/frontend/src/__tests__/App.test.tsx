import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { App } from '../App';
import { AppProviders } from '../main';

const renderWithProviders = () =>
  render(
    <AppProviders googleClientId="test-client">
      <App />
    </AppProviders>,
  );

// ゲスト導線のみに絞ったテストなので /api/config と認証関連エンドポイントを最小レスポンスで固定する。
const setupConfigFetch = () => {
  const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    if (url.endsWith('/api/config')) {
      return Promise.resolve(
        new Response(JSON.stringify({ request_timeout_ms: 60000, llm_model: 'gpt-5.6-luna' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }
    if (url.endsWith('/api/auth/logout')) {
      return Promise.resolve(new Response(null, { status: 204 }));
    }
    if (url.endsWith('/api/auth/guest')) {
      return Promise.resolve(
        new Response(JSON.stringify({ mode: 'guest' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }
    return Promise.resolve(
      new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
  });
  (globalThis as any).fetch = fetchMock;
  return fetchMock;
};

describe('App guest mode entry', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    setupConfigFetch();
    // テスト間の独立性を保つため、前のテストで保存されたゲストモード状態をクリア
    localStorage.clear();
  });

  it('shows the guest button and transitions into guest mode', async () => {
    renderWithProviders();

    const user = userEvent.setup();
    const guestButton = await screen.findByRole('button', { name: 'ゲスト閲覧モード' });

    await act(async () => {
      await user.click(guestButton);
    });

    expect(await screen.findByRole('heading', { name: 'WordPack' })).toBeInTheDocument();
    expect(screen.getByText('ゲスト閲覧モード')).toBeInTheDocument();
  });

  it('closes the sidebar when the backdrop is clicked or Escape is pressed', async () => {
    // モバイルレイアウト（オーバーレイサイドバー）をシミュレート
    // なぜ: バックドロップはオーバーレイ幅（max-width: 900px）でのみ表示される仕様だから
    const mockMatchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query === '(max-width: 900px)',
      media: query,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
      onchange: null,
    }));
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: mockMatchMedia,
    });

    const { container } = renderWithProviders();
    const user = userEvent.setup();

    const guestButton = await screen.findByRole('button', { name: 'ゲスト閲覧モード' });
    await act(async () => {
      await user.click(guestButton);
    });

    const menuButton = await screen.findByRole('button', { name: 'メニューを開く' });
    await act(async () => {
      await user.click(menuButton);
    });

    expect(container.querySelector('.sidebar-backdrop')).toBeInTheDocument();

    await act(async () => {
      await user.keyboard('{Escape}');
    });

    expect(container.querySelector('.sidebar-backdrop')).not.toBeInTheDocument();

    await act(async () => {
      await user.click(menuButton);
    });

    const backdropButton = container.querySelector('.sidebar-backdrop') as HTMLButtonElement | null;
    expect(backdropButton).toBeInTheDocument();
    if (backdropButton) {
      await act(async () => {
        await user.click(backdropButton);
      });
    }

    expect(container.querySelector('.sidebar-backdrop')).not.toBeInTheDocument();
  });
});
