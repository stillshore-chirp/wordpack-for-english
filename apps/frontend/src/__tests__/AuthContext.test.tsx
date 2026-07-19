import { render, waitFor, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import React from 'react';
import { vi } from 'vitest';
import type { MockedFunction } from 'vitest';
import { AuthProvider, useAuth } from '../AuthContext';

const googleProviderMock = vi.fn(
  ({ children }: { clientId?: string; locale?: string; children: React.ReactNode }) => <>{children}</>,
);

vi.mock('@react-oauth/google', () => ({
  GoogleOAuthProvider: ({
    clientId,
    locale,
    children,
  }: {
    clientId: string;
    locale?: string;
    children: React.ReactNode;
  }) => googleProviderMock({ clientId, locale, children }),
}));

const MissingFlagProbe: React.FC = () => {
  const { missingClientId, authMode, isGuest } = useAuth();
  return (
    <span
      data-testid="client-flag"
      data-auth-mode={authMode}
      data-guest={isGuest ? 'true' : 'false'}
    >
      {missingClientId ? 'missing' : 'ok'}
    </span>
  );
};

// 認証コンテキストが ID トークンを公開していないことを検知するための専用プローブ。
// hasOwnProperty を直接用いることで、余計な型キャストを避けつつ漏洩有無を判定する。
const TokenLeakProbe: React.FC = () => {
  const contextValue = useAuth();
  const hasTokenKey = Object.prototype.hasOwnProperty.call(contextValue, 'token');
  return <span data-testid="token-leak">{hasTokenKey ? 'leaked' : 'clean'}</span>;
};

const AuthStateProbe: React.FC = () => {
  const { authMode, user, authBypassActive } = useAuth();
  return (
    <span
      data-testid="auth-state"
      data-auth-mode={authMode}
      data-user={user ? 'present' : 'null'}
      data-bypass={authBypassActive ? 'true' : 'false'}
    />
  );
};

describe('AuthProvider logging behaviour', () => {
  // 新規参画者向けメモ: 認証バイパス有効時のログレベル切り替えを固定するための回帰テスト。
  // バイパス環境では error を抑制し warn に切り替わることをここで保証する。
  let fetchMock: MockedFunction<typeof fetch>;

  beforeEach(() => {
    fetchMock = vi.fn();
    (globalThis as unknown as { fetch: typeof fetch }).fetch = fetchMock;
    googleProviderMock.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const renderProvider = () => {
    render(
      <AuthProvider clientId="">
        <div data-testid="auth-provider-child" />
      </AuthProvider>,
    );
  };

  it('provides missingClientId flag and skips Google provider when client ID is empty', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    render(
      <AuthProvider clientId=" ">
        <MissingFlagProbe />
      </AuthProvider>,
    );

    expect(await screen.findByTestId('client-flag')).toHaveTextContent('missing');
    expect(googleProviderMock).not.toHaveBeenCalled();
  });

  it('uses Google client ID from runtime config when build-time env is empty', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ google_client_id: 'runtime-client.apps.googleusercontent.com' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    render(
      <AuthProvider clientId="">
        <MissingFlagProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId('client-flag')).toHaveTextContent('ok');
    });
    expect(googleProviderMock).toHaveBeenCalledWith(
      expect.objectContaining({
        clientId: 'runtime-client.apps.googleusercontent.com',
        locale: 'ja',
      }),
    );
  });

  it('prefers console.warn when bypass mode supplies a development credential', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : '';
      if (url.endsWith('/api/config')) {
        return Promise.resolve(
          new Response(JSON.stringify({ session_auth_disabled: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    renderProvider();

    await waitFor(() => {
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining('VITE_GOOGLE_CLIENT_ID is not set; Google login will not work.'),
      );
    });
    expect(errorSpy).not.toHaveBeenCalled();
  });

  it('falls back to console.error when bypass is not available', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof Request ? input.url : '';
      if (url.endsWith('/api/config')) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('{}', { status: 200 }));
    });

    renderProvider();

    await waitFor(() => {
      expect(errorSpy).toHaveBeenCalledWith(
        'VITE_GOOGLE_CLIENT_ID is not set; Google login will not work.',
      );
    });
    expect(warnSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('Authentication bypass is active; continuing with development fallback.'),
    );
  });
});

describe('AuthProvider persistence behaviour', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try { localStorage.clear(); } catch { /* ignore */ }
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('persists user information without ID token leakage', async () => {
    const sampleUser = {
      google_sub: 'sub-123',
      email: 'tester@example.com',
      display_name: 'Tester',
    };

    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/google') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(
            JSON.stringify({ user: sampleUser }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    const setItemSpy = vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem');

    const SignInProbe: React.FC = () => {
      const { signIn, user } = useAuth();
      React.useEffect(() => {
        if (!user) {
          void (signIn('dummy-id-token').catch(() => undefined));
        }
      }, [signIn, user]);
      return null;
    };

    render(
      <AuthProvider clientId="test-client">
        <SignInProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/api/auth/google'),
        expect.objectContaining({ method: 'POST' }),
      );
    });

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith(
        'wordpack.auth.v1',
        expect.any(String),
      );
    });

    const [, storedValue] = setItemSpy.mock.calls[setItemSpy.mock.calls.length - 1];
    const payload = JSON.parse(storedValue as string) as Record<string, unknown>;

    expect(payload).toHaveProperty('authMode', 'authenticated');
    expect(payload).toHaveProperty('user');
    expect(payload).not.toHaveProperty('token');
    expect(payload.user).toMatchObject(sampleUser);

    setItemSpy.mockRestore();
  });

  it('stores guest mode state for later restoration', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(JSON.stringify({ mode: 'guest' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    const setItemSpy = vi.spyOn(Object.getPrototypeOf(window.localStorage), 'setItem');

    const GuestModeProbe: React.FC = () => {
      const { enterGuestMode } = useAuth();
      React.useEffect(() => {
        void enterGuestMode();
      }, [enterGuestMode]);
      return null;
    };

    render(
      <AuthProvider clientId="test-client">
        <GuestModeProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(setItemSpy).toHaveBeenCalledWith(
        'wordpack.auth.v1',
        expect.stringContaining('"authMode":"guest"'),
      );
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/config', { method: 'GET' });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/logout',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/auth/guest',
      expect.objectContaining({ method: 'POST' }),
    );

    setItemSpy.mockRestore();
  });

  it('requests guest session and surfaces an error on failure', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Guest session failed' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    const GuestErrorProbe: React.FC = () => {
      const { enterGuestMode, error, authMode } = useAuth();
      React.useEffect(() => {
        void enterGuestMode();
      }, [enterGuestMode]);
      return (
        <span data-testid="guest-error" data-auth-mode={authMode}>
          {error ?? 'none'}
        </span>
      );
    };

    render(
      <AuthProvider clientId="test-client">
        <GuestErrorProbe />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/logout',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/guest',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('guest-error')).toHaveTextContent(
        'ゲストモードの開始に失敗しました。しばらくしてから再試行してください。',
      );
    });
    expect(screen.getByTestId('guest-error')).toHaveAttribute('data-auth-mode', 'anonymous');
  });
});

describe('AuthProvider public API surface', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try { localStorage.clear(); } catch { /* ignore */ }
  });

  it('does not expose token field via context value', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    render(
      <AuthProvider clientId="test-client">
        <TokenLeakProbe />
      </AuthProvider>,
    );

    expect(await screen.findByTestId('token-leak')).toHaveTextContent('clean');
    expect(fetchMock).toHaveBeenCalledWith('/api/config', { method: 'GET' });
  });

  it('restores guest mode from localStorage and exposes guest flags', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({}), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));

    render(
      <AuthProvider clientId="test-client">
        <MissingFlagProbe />
      </AuthProvider>,
    );

    const flag = await screen.findByTestId('client-flag');
    expect(flag).toHaveAttribute('data-auth-mode', 'guest');
    expect(flag).toHaveAttribute('data-guest', 'true');
    expect(fetchMock).toHaveBeenCalledWith('/api/config', { method: 'GET' });
  });

  it('does not inject bypass user while restoring guest mode even when /api/config resolves fast', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ session_auth_disabled: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));

    render(
      <AuthProvider clientId="test-client">
        <AuthStateProbe />
      </AuthProvider>,
    );

    const state = await screen.findByTestId('auth-state');
    await waitFor(() => {
      expect(state).toHaveAttribute('data-auth-mode', 'guest');
      expect(state).toHaveAttribute('data-user', 'null');
      expect(state).toHaveAttribute('data-bypass', 'true');
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/config', { method: 'GET' });
  });
});

describe('AuthProvider unauthorized guest recovery', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    try { localStorage.clear(); } catch { /* ignore */ }
  });

  const UnauthorizedProbe: React.FC = () => {
    const { authMode, error } = useAuth();
    return (
      <span data-testid="unauthorized-probe" data-auth-mode={authMode}>
        {error ?? 'none'}
      </span>
    );
  };

  it('reissues guest session when unauthorized while in guest mode', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(JSON.stringify({ mode: 'guest' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));

    render(
      <AuthProvider clientId="test-client">
        <UnauthorizedProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('unauthorized-probe');
    expect(probe).toHaveAttribute('data-auth-mode', 'guest');

    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/guest',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'guest');
      expect(probe).toHaveTextContent('none');
    });
  });

  it('falls back to anonymous when guest reissue fails on unauthorized', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: 'Guest session failed' }), {
            status: 500,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));

    render(
      <AuthProvider clientId="test-client">
        <UnauthorizedProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('unauthorized-probe');
    expect(probe).toHaveAttribute('data-auth-mode', 'guest');

    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/auth/guest',
        expect.objectContaining({ method: 'POST' }),
      );
    });

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveTextContent(
        'ゲストセッションの再発行に失敗しました。しばらくしてから再試行してください。',
      );
    });
  });

  it('prevents concurrent guest reissue requests when multiple 401s occur simultaneously', async () => {
    let guestCallCount = 0;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config') && (!init || init.method === 'GET' || !init.method)) {
        return Promise.resolve(
          new Response(JSON.stringify({}), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') {
        guestCallCount++;
        // 並行リクエストの競合を模倣: 最初の呼び出しは成功
        return Promise.resolve(
          new Response(JSON.stringify({ mode: 'guest' }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          }),
        );
      }
      return Promise.resolve(new Response('not found', { status: 404 }));
    });

    window.localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));

    render(
      <AuthProvider clientId="test-client">
        <UnauthorizedProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('unauthorized-probe');
    expect(probe).toHaveAttribute('data-auth-mode', 'guest');

    // 複数の 401 を同時に発火して並行呼び出しをシミュレート
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));

    // 単一実行ガードにより、最初のリクエストのみが実行されることを検証
    await waitFor(() => {
      expect(guestCallCount).toBe(1);
    });

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'guest');
      expect(probe).toHaveTextContent('none');
    });
  });
});
