import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider, LOGOUT_REQUEST_TIMEOUT_MS } from '../AuthContext';
import { LoginScreen } from './LoginScreen';

describe('LoginScreen logout recovery', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  const setupDeferredLogout = (response: Response | Promise<Response>) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') return Promise.resolve(response);
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    return fetchMock;
  };

  const renderRecoveryScreen = () => {
    localStorage.setItem('wordpack.logout.v1', JSON.stringify({ outcome: 'failed' }));
    return render(
      <AuthProvider clientId="test-client">
        <LoginScreen />
      </AuthProvider>,
    );
  };

  it('moves focus to the login heading after recovery succeeds', async () => {
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({
      authMode: 'authenticated',
      user: { google_sub: 'stale', email: 'stale@example.com', display_name: 'Stale' },
    }));
    localStorage.setItem('wordpack.logout.v1', JSON.stringify({ outcome: 'failed' }));
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) return logoutResponse;
      return Promise.resolve(new Response('{}', { status: 404 }));
    });

    render(
      <AuthProvider clientId="">
        <LoginScreen />
      </AuthProvider>,
    );

    const retry = await screen.findByRole('button', { name: 'ログアウトを再試行' });
    await userEvent.setup().click(retry);
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent('ログアウトしています');
      expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite');
    });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).not.toHaveTextContent('ログアウトに失敗しました');

    await act(async () => {
      resolveLogout(new Response(null, { status: 204 }));
    });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Google ログインの設定が必要です' })).toHaveFocus();
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.queryByText('ログアウトに失敗しました')).not.toBeInTheDocument();
  });

  it('announces a polite pending state before showing a failed logout response', async () => {
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    setupDeferredLogout(logoutResponse);
    renderRecoveryScreen();
    const retry = await screen.findByRole('button', { name: 'ログアウトを再試行' });

    await act(async () => {
      fireEvent.click(retry);
    });
    expect(screen.getByRole('status')).toHaveTextContent('サーバー側のセッション状態を確認中です');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    await act(async () => {
      resolveLogout(new Response('{}', { status: 503 }));
    });
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('ログアウトに失敗しました');
      expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive');
    });
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('keeps the pending announcement polite until a bounded timeout becomes unknown', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') return new Promise<Response>(() => undefined);
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    renderRecoveryScreen();
    const retry = screen.getByRole('button', { name: 'ログアウトを再試行' });

    await act(async () => {
      fireEvent.click(retry);
    });
    expect(screen.getByRole('status')).toHaveTextContent('ログアウトしています');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(LOGOUT_REQUEST_TIMEOUT_MS);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('ログアウトの結果を確認できませんでした');
    expect(screen.getByRole('alert')).toHaveAttribute('aria-live', 'assertive');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('disables guest entry while authentication is in progress', async () => {
    let resolveGuest!: (response: Response) => void;
    const guestResponse = new Promise<Response>((resolve) => {
      resolveGuest = resolve;
    });
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) return Promise.resolve(new Response(null, { status: 204 }));
      if (url.endsWith('/api/auth/guest')) return guestResponse;
      return Promise.resolve(new Response('{}', { status: 404 }));
    });

    render(
      <AuthProvider clientId="">
        <LoginScreen />
      </AuthProvider>,
    );

    const guestButton = await screen.findByRole('button', { name: 'ゲスト閲覧モード' });
    await userEvent.setup().click(guestButton);
    await waitFor(() => expect(screen.getByRole('button', { name: 'ゲスト閲覧モード' })).toBeDisabled());

    await resolveGuest(new Response(JSON.stringify({ mode: 'guest' }), { status: 200 }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'ゲスト閲覧モード' })).not.toBeDisabled());
  });
});
