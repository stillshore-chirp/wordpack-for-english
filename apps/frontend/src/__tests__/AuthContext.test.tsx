import { act, render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import React from 'react';
import { vi } from 'vitest';
import type { MockedFunction } from 'vitest';
import { AuthProvider, LOGOUT_REQUEST_TIMEOUT_MS, useAuth } from '../AuthContext';

const LOGOUT_CONFIRMATION_RECEIPT_KEY = 'wordpack.logout.confirmed.v1';

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

const LogoutStateProbe: React.FC = () => {
  const { authMode, user, error, logoutOutcome, isAuthenticating, authBypassActive, signOut } = useAuth();
  return (
    <>
      <span
        data-testid="logout-state"
        data-auth-mode={authMode}
        data-user={user ? 'present' : 'null'}
        data-outcome={logoutOutcome ?? 'none'}
        data-authenticating={isAuthenticating ? 'true' : 'false'}
        data-bypass={authBypassActive ? 'true' : 'false'}
      >
        {error ?? 'none'}
      </span>
      <button type="button" onClick={() => signOut()}>ログアウト</button>
    </>
  );
};

const AuthRecoveryProbe: React.FC = () => {
  const { authMode, user, logoutOutcome, signIn, signOut, enterGuestMode } = useAuth();
  return (
    <>
      <span
        data-testid="auth-recovery-state"
        data-auth-mode={authMode}
        data-user={user ? 'present' : 'null'}
        data-outcome={logoutOutcome ?? 'none'}
      />
      <button type="button" onClick={() => void signIn('reload-token').catch(() => undefined)}>サインイン</button>
      <button type="button" onClick={() => void enterGuestMode()}>ゲスト</button>
      <button type="button" onClick={() => void signOut()}>ログアウト</button>
    </>
  );
};

class TestBroadcastChannel {
  static instances: TestBroadcastChannel[] = [];

  readonly name: string;
  readonly sentMessages: unknown[] = [];
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  private closed = false;

  constructor(name: string) {
    this.name = name;
    TestBroadcastChannel.instances.push(this);
  }

  postMessage(message: unknown): void {
    this.sentMessages.push(message);
    for (const target of TestBroadcastChannel.instances) {
      if (target === this || target.closed || target.name !== this.name) continue;
      Promise.resolve().then(() => target.onmessage?.({ data: message } as MessageEvent<unknown>));
    }
  }

  close(): void {
    this.closed = true;
    const index = TestBroadcastChannel.instances.indexOf(this);
    if (index >= 0) TestBroadcastChannel.instances.splice(index, 1);
  }

  static reset(): void {
    TestBroadcastChannel.instances = [];
  }
}

function installBroadcastChannel(value: unknown): () => void {
  const descriptor = Object.getOwnPropertyDescriptor(window, 'BroadcastChannel');
  Object.defineProperty(window, 'BroadcastChannel', {
    configurable: true,
    writable: true,
    value,
  });
  return () => {
    if (descriptor) {
      Object.defineProperty(window, 'BroadcastChannel', descriptor);
    } else {
      delete (window as Window & { BroadcastChannel?: unknown }).BroadcastChannel;
    }
  };
}

function installNavigationType(type: string | null): () => void {
  const getEntriesByTypeSpy = vi.spyOn(performance, 'getEntriesByType').mockReturnValue(
    type === null ? [] : [{ type } as unknown as PerformanceNavigationTiming],
  );
  return () => getEntriesByTypeSpy.mockRestore();
}

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
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {
      // storage reset is best-effort in access-denied tests.
    }
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

  it('keeps a runtime Google client ID when config resolves after logout invalidates auth state', async () => {
    localStorage.clear();
    sessionStorage.clear();
    let resolveConfig!: (response: Response) => void;
    const configResponse = new Promise<Response>((resolve) => {
      resolveConfig = resolve;
    });
    fetchMock.mockImplementationOnce(() => configResponse);

    render(
      <AuthProvider clientId="">
        <MissingFlagProbe />
      </AuthProvider>,
    );

    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        newValue: JSON.stringify({ outcome: 'unknown' }),
        storageArea: window.localStorage,
      }));
    });
    await act(async () => {
      resolveConfig(new Response(JSON.stringify({ google_client_id: 'late-runtime-client.apps.googleusercontent.com' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('client-flag')).toHaveTextContent('ok');
      expect(googleProviderMock).toHaveBeenCalledWith(
        expect.objectContaining({
          clientId: 'late-runtime-client.apps.googleusercontent.com',
          locale: 'ja',
        }),
      );
    });
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

describe('AuthProvider logout result state', () => {
  const sampleUser = {
    google_sub: 'sub-logout',
    email: 'logout@example.com',
    display_name: 'Logout Tester',
  };

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'authenticated', user: sampleUser }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  const setupFetch = (logoutResponse: Response | Promise<Response> | undefined, rejectLogout = false) => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) {
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }));
      }
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') {
        if (rejectLogout) return Promise.reject(new Error('network unavailable'));
        return Promise.resolve(logoutResponse as Response);
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    return fetchMock;
  };

  it.each([200, 204])('treats HTTP %s as confirmed server-side logout', async (status) => {
    const fetchMock = setupFetch(new Response(null, { status }));
    const user = userEvent.setup();

    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('logout-state');
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-user', 'null');
      expect(probe).toHaveAttribute('data-outcome', 'confirmed');
    });
    expect(localStorage.getItem('wordpack.auth.v1')).toBeNull();
    expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ method: 'POST' }));
  });

  it('does not re-inject a development bypass user after confirmed logout', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) {
        return Promise.resolve(new Response(JSON.stringify({ session_auth_disabled: true }), { status: 200 }));
      }
      if (url.endsWith('/api/auth/logout')) return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const user = userEvent.setup();

    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('logout-state');
    await waitFor(() => expect(probe).toHaveAttribute('data-bypass', 'true'));
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-user', 'null');
      expect(probe).toHaveAttribute('data-outcome', 'confirmed');
      expect(probe).toHaveAttribute('data-bypass', 'false');
    });
    expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/google', expect.anything());
  });

  it('treats a non-success HTTP response as failed and keeps a retry marker', async () => {
    setupFetch(new Response('{}', { status: 503 }));
    const user = userEvent.setup();

    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('logout-state');
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-outcome', 'failed');
      expect(probe).toHaveTextContent('サーバー側のセッションは終了していない可能性があります');
    });
    expect(localStorage.getItem('wordpack.auth.v1')).toBeNull();
    expect(localStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'failed' }));
  });

  it('clears personal state and persists an unknown marker before a logout response arrives', async () => {
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) return logoutResponse;
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    localStorage.setItem('wpfe.notifications.v1', JSON.stringify([{ id: 'private-job' }]));
    sessionStorage.setItem('wp.list.ui_state.v1', JSON.stringify({ selected: 'private-pack' }));
    const user = userEvent.setup();

    const firstRender = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('logout-state');
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-user', 'null');
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      expect(probe).toHaveAttribute('data-authenticating', 'true');
    });
    expect(localStorage.getItem('wordpack.auth.v1')).toBeNull();
    expect(localStorage.getItem('wpfe.notifications.v1')).toBeNull();
    expect(sessionStorage.getItem('wp.list.ui_state.v1')).toBeNull();
    expect(localStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'unknown' }));

    firstRender.unmount();
    const secondRender = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const reloadedProbe = screen.getByTestId('logout-state');
    expect(reloadedProbe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(reloadedProbe).toHaveAttribute('data-user', 'null');
    expect(reloadedProbe).toHaveAttribute('data-outcome', 'unknown');

    secondRender.unmount();
    await act(async () => {
      resolveLogout(new Response(null, { status: 204 }));
    });
    expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it.each([
    ['network failure', true, undefined],
    ['lost response', false, undefined],
  ])('treats %s as unknown server-side outcome', async (_label, rejectLogout, response) => {
    setupFetch(response, rejectLogout);
    const user = userEvent.setup();

    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );

    const probe = await screen.findByTestId('logout-state');
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));

    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      expect(probe).toHaveTextContent('サーバー側のセッション状態は未確認です');
    });
    expect(localStorage.getItem('wordpack.auth.v1')).toBeNull();
    expect(localStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'unknown' }));
  });

  it('restores unresolved logout state after reload and blocks auth restoration', async () => {
    setupFetch(new Response('{}', { status: 500 }));
    const user = userEvent.setup();
    const firstRender = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));
    await waitFor(() => expect(screen.getByTestId('logout-state')).toHaveAttribute('data-outcome', 'failed'));
    firstRender.unmount();

    const fetchMock = setupFetch(new Response('{}', { status: 200 }));
    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('logout-state');
    expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(probe).toHaveAttribute('data-user', 'null');
    expect(probe).toHaveAttribute('data-outcome', 'failed');
    expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/google', expect.anything());
  });

  it('allows the recovery UI state to be retried after a lost response', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) {
        const logoutCalls = fetchMock.mock.calls.filter(([request]) => {
          const requestUrl = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
          return requestUrl.endsWith('/api/auth/logout');
        }).length;
        return logoutCalls === 1
          ? Promise.resolve(undefined as unknown as Response)
          : Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const user = userEvent.setup();

    render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('logout-state');
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));
    await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'unknown'));

    await user.click(screen.getByRole('button', { name: 'ログアウト' }));
    await waitFor(() => {
      expect(probe).toHaveAttribute('data-outcome', 'confirmed');
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    });
    expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
    expect(fetchMock.mock.calls.filter(([request]) => {
      const requestUrl = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
      return requestUrl.endsWith('/api/auth/logout');
    })).toHaveLength(2);
  });

  it('marks a hung logout as unknown after a bounded timeout and enables retry', async () => {
    vi.useFakeTimers();
    try {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
        if (url.endsWith('/api/auth/logout')) return new Promise<Response>(() => undefined);
        return Promise.resolve(new Response('{}', { status: 404 }));
      });
      render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = screen.getByTestId('logout-state');
      await act(async () => {
        screen.getByRole('button', { name: 'ログアウト' }).click();
      });
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      expect(probe).toHaveAttribute('data-authenticating', 'true');
      expect(localStorage.getItem('wordpack.auth.v1')).toBeNull();

      await act(async () => {
        vi.advanceTimersByTime(LOGOUT_REQUEST_TIMEOUT_MS);
      });
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      expect(probe).toHaveAttribute('data-authenticating', 'false');
      expect(localStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'unknown' }));
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ signal: expect.any(AbortSignal) }));
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses sessionStorage when localStorage access is denied and still sends logout', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'authenticated', user: sampleUser }));
    sessionStorage.clear();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('storage access denied');
      },
    });

    try {
      const fetchMock = setupFetch(new Response(null, { status: 204 }));
      const user = userEvent.setup();
      const rendered = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('logout-state');
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'confirmed'));
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.objectContaining({ method: 'POST' }));
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBe(JSON.stringify({ outcome: 'confirmed' }));
      rendered.unmount();
    } finally {
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('requires a confirmed receipt before authentication in a fresh session-only tab', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    localStorage.clear();
    sessionStorage.clear();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });

    let logoutStatus = 503;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) {
        return Promise.resolve(new Response(logoutStatus === 204 ? null : '{}', { status: logoutStatus }));
      }
      if (url.endsWith('/api/auth/google')) return Promise.resolve(new Response(JSON.stringify({ user: sampleUser }), { status: 200 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    let restoreNavigation: (() => void) | undefined;

    try {
      const rendered = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('auth-recovery-state');
      expect(probe).toHaveAttribute('data-outcome', 'unknown');

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: 'サインイン' }));
      await user.click(screen.getByRole('button', { name: 'ゲスト' }));
      expect(fetchMock.mock.calls.filter(([request]) => {
        const url = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
        return url.endsWith('/api/auth/google') || url.endsWith('/api/auth/guest');
      })).toHaveLength(0);

      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'failed'));
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'failed' }));
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();

      logoutStatus = 204;
      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'confirmed'));
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBeNull();
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBe(JSON.stringify({ outcome: 'confirmed' }));
      rendered.unmount();

      restoreNavigation = installNavigationType('reload');
      const reloaded = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const reloadedProbe = await screen.findByTestId('auth-recovery-state');
      expect(reloadedProbe).toHaveAttribute('data-outcome', 'none');
      await user.click(screen.getByRole('button', { name: 'サインイン' }));
      await waitFor(() => {
        expect(reloadedProbe).toHaveAttribute('data-auth-mode', 'authenticated');
        expect(reloadedProbe).toHaveAttribute('data-user', 'present');
      });
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/google', expect.objectContaining({ method: 'POST' }));
      reloaded.unmount();
    } finally {
      restoreNavigation?.();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it.each(['navigate', 'back_forward', null] as const)(
    'rejects a copied session-only confirmation receipt on %s navigation and keeps it rejected after reload',
    async (navigationType) => {
      const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
      if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
      const restoreBroadcastChannel = installBroadcastChannel(undefined);
      TestBroadcastChannel.reset();
      localStorage.clear();
      sessionStorage.clear();
      sessionStorage.setItem(LOGOUT_CONFIRMATION_RECEIPT_KEY, JSON.stringify({ outcome: 'confirmed' }));
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        get: () => {
          throw new Error('localStorage access denied');
        },
      });
      let restoreNavigation = installNavigationType(navigationType);
      let rendered: ReturnType<typeof render> | undefined;
      try {
        setupFetch(new Response('{}', { status: 200 }));
        rendered = render(
          <AuthProvider clientId="test-client">
            <AuthRecoveryProbe />
          </AuthProvider>,
        );
        const probe = await screen.findByTestId('auth-recovery-state');
        expect(probe).toHaveAttribute('data-outcome', 'unknown');
        expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();
        rendered.unmount();

        restoreNavigation();
        restoreNavigation = installNavigationType('reload');
        rendered = render(
          <AuthProvider clientId="test-client">
            <AuthRecoveryProbe />
          </AuthProvider>,
        );
        expect(await screen.findByTestId('auth-recovery-state')).toHaveAttribute('data-outcome', 'unknown');
      } finally {
        rendered?.unmount();
        restoreNavigation();
        Object.defineProperty(window, 'localStorage', localStorageDescriptor);
        restoreBroadcastChannel();
      }
    },
  );

  it('allows authentication when sessionStorage is unavailable but localStorage is usable', async () => {
    const sessionStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'sessionStorage');
    if (!sessionStorageDescriptor) throw new Error('sessionStorage descriptor is unavailable');
    Object.defineProperty(window, 'sessionStorage', {
      configurable: true,
      get: () => {
        throw new Error('sessionStorage access denied');
      },
    });

    let logoutStatus = 503;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) {
        return Promise.resolve(new Response(logoutStatus === 204 ? null : '{}', { status: logoutStatus }));
      }
      if (url.endsWith('/api/auth/google')) return Promise.resolve(new Response(JSON.stringify({ user: sampleUser }), { status: 200 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });

    try {
      const rendered = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('auth-recovery-state');
      expect(probe).toHaveAttribute('data-outcome', 'none');

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'failed'));
      expect(localStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'failed' }));

      logoutStatus = 204;
      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'confirmed'));
      expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
      rendered.unmount();

      const reloaded = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const reloadedProbe = await screen.findByTestId('auth-recovery-state');
      expect(reloadedProbe).toHaveAttribute('data-outcome', 'none');
      await user.click(screen.getByRole('button', { name: 'サインイン' }));
      await waitFor(() => {
        expect(reloadedProbe).toHaveAttribute('data-auth-mode', 'authenticated');
        expect(reloadedProbe).toHaveAttribute('data-user', 'present');
      });
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/google', expect.objectContaining({ method: 'POST' }));
      reloaded.unmount();
    } finally {
      Object.defineProperty(window, 'sessionStorage', sessionStorageDescriptor);
    }
  });

  it('keeps a recovery marker in sessionStorage when localStorage writes fail', async () => {
    const localStorageObject = window.localStorage;
    const storagePrototype = Object.getPrototypeOf(localStorageObject) as Storage;
    const originalSetItem = storagePrototype.setItem;
    const setItemSpy = vi.spyOn(storagePrototype, 'setItem').mockImplementation(function (this: Storage, key, value) {
      if (this === localStorageObject && key === 'wordpack.logout.v1') {
        throw new Error('localStorage quota exceeded');
      }
      return originalSetItem.call(this, key, value);
    });

    try {
      setupFetch(new Response('{}', { status: 503 }));
      const user = userEvent.setup();
      const rendered = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('logout-state');
      await user.click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'failed'));
      expect(localStorageObject.getItem('wordpack.logout.v1')).toBeNull();
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'failed' }));
      rendered.unmount();
    } finally {
      setItemSpy.mockRestore();
    }

    setupFetch(new Response('{}', { status: 200 }));
    const reloaded = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    expect(await screen.findByTestId('logout-state')).toHaveAttribute('data-outcome', 'failed');
    reloaded.unmount();
  });

  it('applies logout recovery changes received from another tab', async () => {
    setupFetch(new Response('{}', { status: 200 }));
    const rendered = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('logout-state');

    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        newValue: JSON.stringify({ outcome: 'unknown' }),
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(probe).toHaveAttribute('data-outcome', 'unknown');
    expect(sessionStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'unknown' }));

    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        oldValue: JSON.stringify({ outcome: 'unknown' }),
        newValue: null,
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(probe).toHaveAttribute('data-outcome', 'confirmed');
    expect(sessionStorage.getItem('wordpack.logout.v1')).toBeNull();
    rendered.unmount();
  });

  it('uses BroadcastChannel for session-only recovery and propagates retry confirmation', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });

    let logoutStatus = 503;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') {
        return Promise.resolve(new Response(logoutStatus === 204 ? null : '{}', { status: logoutStatus }));
      }
      return Promise.resolve(new Response('{}', { status: 404 }));
    });

    const DualProbe: React.FC<{ id: string }> = ({ id }) => {
      const { authMode, user, error, logoutOutcome, signOut } = useAuth();
      return (
        <div>
          <span
            data-testid={`broadcast-state-${id}`}
            data-auth-mode={authMode}
            data-user={user ? 'present' : 'null'}
            data-outcome={logoutOutcome ?? 'none'}
          >
            {error ?? 'none'}
          </span>
          <button type="button" onClick={() => void signOut()}>ログアウト {id}</button>
        </div>
      );
    };

    let rendered: ReturnType<typeof render> | undefined;
    try {
      rendered = render(
        <>
          <AuthProvider clientId="test-client"><DualProbe id="A" /></AuthProvider>
          <AuthProvider clientId="test-client"><DualProbe id="B" /></AuthProvider>
        </>,
      );
      const probeA = await screen.findByTestId('broadcast-state-A');
      const probeB = await screen.findByTestId('broadcast-state-B');
      await waitFor(() => expect(TestBroadcastChannel.instances).toHaveLength(2));

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: 'ログアウト A' }));
      await waitFor(() => {
        expect(probeA).toHaveAttribute('data-outcome', 'failed');
        expect(probeB).toHaveAttribute('data-outcome', 'failed');
        expect(probeA).toHaveAttribute('data-auth-mode', 'anonymous');
        expect(probeB).toHaveAttribute('data-user', 'null');
      });

      logoutStatus = 204;
      await user.click(screen.getByRole('button', { name: 'ログアウト A' }));
      await waitFor(() => {
        expect(probeA).toHaveAttribute('data-outcome', 'confirmed');
        expect(probeB).toHaveAttribute('data-outcome', 'confirmed');
      });
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBeNull();
      expect(fetchMock.mock.calls.filter(([request]) => {
        const url = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
        return url.endsWith('/api/auth/logout');
      })).toHaveLength(2);
    } finally {
      rendered?.unmount();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('keeps a one-tab confirmed result when BroadcastChannel has no receiver', async () => {
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    let rendered: ReturnType<typeof render> | undefined;
    try {
      setupFetch(new Response(null, { status: 204 }));
      rendered = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('logout-state');
      await waitFor(() => expect(TestBroadcastChannel.instances).toHaveLength(1));

      await act(async () => {
        TestBroadcastChannel.instances[0]?.onmessage?.({
          data: { type: 'other-message', version: 1, outcome: 'failed' },
        } as MessageEvent<unknown>);
      });
      expect(probe).toHaveAttribute('data-outcome', 'none');

      await userEvent.setup().click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'confirmed'));
      expect(TestBroadcastChannel.instances[0]?.sentMessages).toEqual([
        { type: 'logout-recovery', version: 1, outcome: 'unknown' },
        { type: 'logout-recovery', version: 1, outcome: 'confirmed' },
      ]);
    } finally {
      rendered?.unmount();
      restoreBroadcastChannel();
    }
  });

  it('invalidates a session-only confirmation receipt on later failed or unknown logout state', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    const restoreNavigation = installNavigationType('reload');
    localStorage.clear();
    sessionStorage.clear();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });
    sessionStorage.setItem(LOGOUT_CONFIRMATION_RECEIPT_KEY, JSON.stringify({ outcome: 'confirmed' }));
    let rendered: ReturnType<typeof render> | undefined;
    try {
      setupFetch(new Response('{}', { status: 200 }));
      rendered = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('auth-recovery-state');
      expect(probe).toHaveAttribute('data-outcome', 'none');

      await act(async () => {
        window.dispatchEvent(new StorageEvent('storage', {
          key: 'wordpack.logout.v1',
          newValue: JSON.stringify({ outcome: 'failed' }),
        }));
      });
      expect(probe).toHaveAttribute('data-outcome', 'failed');
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();

      sessionStorage.setItem(LOGOUT_CONFIRMATION_RECEIPT_KEY, JSON.stringify({ outcome: 'confirmed' }));
      await act(async () => {
        window.dispatchEvent(new StorageEvent('storage', {
          key: 'wordpack.logout.v1',
          oldValue: JSON.stringify({ outcome: 'failed' }),
          newValue: JSON.stringify({ outcome: 'unknown' }),
        }));
      });
      expect(probe).toHaveAttribute('data-outcome', 'unknown');
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();
    } finally {
      rendered?.unmount();
      restoreNavigation();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('invalidates a session-only confirmation receipt when a session request starts', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    const restoreNavigation = installNavigationType('reload');
    localStorage.clear();
    sessionStorage.clear();
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });
    sessionStorage.setItem(LOGOUT_CONFIRMATION_RECEIPT_KEY, JSON.stringify({ outcome: 'confirmed' }));
    let rendered: ReturnType<typeof render> | undefined;
    try {
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
        if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
        if (url.endsWith('/api/auth/google') && init?.method === 'POST') {
          return Promise.resolve(new Response(JSON.stringify({ user: sampleUser }), { status: 200 }));
        }
        return Promise.resolve(new Response('{}', { status: 404 }));
      });
      rendered = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('auth-recovery-state');
      expect(probe).toHaveAttribute('data-outcome', 'none');

      await userEvent.setup().click(screen.getByRole('button', { name: 'サインイン' }));
      await waitFor(() => {
        expect(probe).toHaveAttribute('data-auth-mode', 'authenticated');
        expect(probe).toHaveAttribute('data-user', 'present');
      });
      expect(fetchMock).toHaveBeenCalledWith('/api/auth/google', expect.objectContaining({ method: 'POST' }));
      expect(sessionStorage.getItem(LOGOUT_CONFIRMATION_RECEIPT_KEY)).toBeNull();
    } finally {
      rendered?.unmount();
      restoreNavigation();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('keeps logout unresolved when localStorage and BroadcastChannel are both unavailable', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const throwingBroadcastChannel = class {
      constructor(_name: string) {
        throw new Error('BroadcastChannel unavailable');
      }
    };
    const restoreBroadcastChannel = installBroadcastChannel(throwingBroadcastChannel);
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });
    let rendered: ReturnType<typeof render> | undefined;
    try {
      setupFetch(new Response(null, { status: 204 }));
      rendered = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('logout-state');
      await userEvent.setup().click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'unknown'));
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBe(JSON.stringify({ outcome: 'unknown' }));
    } finally {
      rendered?.unmount();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('fails closed at startup and blocks sign-in and guest entry without a sync transport', async () => {
    const localStorageDescriptor = Object.getOwnPropertyDescriptor(window, 'localStorage');
    if (!localStorageDescriptor) throw new Error('localStorage descriptor is unavailable');
    const throwingBroadcastChannel = class {
      constructor(_name: string) {
        throw new Error('BroadcastChannel unavailable');
      }
    };
    const restoreBroadcastChannel = installBroadcastChannel(throwingBroadcastChannel);
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage access denied');
      },
    });
    let rendered: ReturnType<typeof render> | undefined;
    try {
      const fetchMock = setupFetch(new Response(null, { status: 204 }));
      rendered = render(
        <AuthProvider clientId="test-client">
          <AuthRecoveryProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('auth-recovery-state');
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-outcome', 'unknown');

      const user = userEvent.setup();
      await user.click(screen.getByRole('button', { name: 'サインイン' }));
      await user.click(screen.getByRole('button', { name: 'ゲスト' }));
      expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/google', expect.anything());
      expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/guest', expect.anything());
    } finally {
      rendered?.unmount();
      Object.defineProperty(window, 'localStorage', localStorageDescriptor);
      restoreBroadcastChannel();
    }
  });

  it('keeps localStorage logout confirmation when BroadcastChannel is unavailable', async () => {
    const restoreBroadcastChannel = installBroadcastChannel(undefined);
    let rendered: ReturnType<typeof render> | undefined;
    try {
      setupFetch(new Response(null, { status: 204 }));
      rendered = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const probe = await screen.findByTestId('logout-state');
      await userEvent.setup().click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(probe).toHaveAttribute('data-outcome', 'confirmed'));
      expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
    } finally {
      rendered?.unmount();
      restoreBroadcastChannel();
    }
  });

  it('drains a pending Google session before confirming a cross-tab logout', async () => {
    localStorage.removeItem('wordpack.auth.v1');
    let resolveGoogle!: (response: Response) => void;
    const googleResponse = new Promise<Response>((resolve) => {
      resolveGoogle = resolve;
    });
    let resolveLogout!: (response: Response) => void;
    const logoutResponse = new Promise<Response>((resolve) => {
      resolveLogout = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/google')) return googleResponse;
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') return logoutResponse;
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const logoutCallCount = () => fetchMock.mock.calls.filter(([request]) => {
      const url = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
      return url.endsWith('/api/auth/logout');
    }).length;
    const RaceProbe: React.FC = () => {
      const { signIn, authMode, user, logoutOutcome, isAuthenticating } = useAuth();
      return (
        <>
          <span
            data-testid="cross-tab-google-state"
            data-auth-mode={authMode}
            data-user={user ? 'present' : 'null'}
            data-outcome={logoutOutcome ?? 'none'}
            data-authenticating={isAuthenticating ? 'true' : 'false'}
          />
          <button type="button" onClick={() => void signIn('cross-tab-token').catch(() => undefined)}>サインイン</button>
        </>
      );
    };

    render(
      <AuthProvider clientId="test-client">
        <RaceProbe />
      </AuthProvider>,
    );
    const user = userEvent.setup();
    const probe = await screen.findByTestId('cross-tab-google-state');
    await user.click(screen.getByRole('button', { name: 'サインイン' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/auth/google', expect.objectContaining({ method: 'POST' })));

    // 発行応答がstorageのlogout開始通知より先にsettleしても、dirty履歴を保持する。
    await act(async () => {
      resolveGoogle(new Response(JSON.stringify({ user: sampleUser }), { status: 200 }));
    });
    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'authenticated');
      expect(probe).toHaveAttribute('data-user', 'present');
    });

    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        newValue: JSON.stringify({ outcome: 'unknown' }),
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(probe).toHaveAttribute('data-user', 'null');
    expect(probe).toHaveAttribute('data-outcome', 'unknown');
    expect(probe).toHaveAttribute('data-authenticating', 'false');
    expect(logoutCallCount()).toBe(0);

    // settle後にconfirmed配送が遅れても、dirty履歴から再確認する。
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        oldValue: JSON.stringify({ outcome: 'unknown' }),
        newValue: null,
        storageArea: window.localStorage,
      }));
    });
    await waitFor(() => expect(logoutCallCount()).toBe(1));
    expect(fetchMock.mock.calls.map(([request]) => typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url))
      .toEqual(['/api/config', '/api/auth/google', '/api/auth/logout']);

    // 進行中の再確認を別tabのunknown通知でstale扱いにせず、自処理の結果を維持する。
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        newValue: JSON.stringify({ outcome: 'failed' }),
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-outcome', 'unknown');
    expect(probe).toHaveAttribute('data-authenticating', 'true');
    expect(logoutCallCount()).toBe(1);

    // confirmedの二重通知も同様にstale化せず、204の結果を維持する。
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        oldValue: JSON.stringify({ outcome: 'unknown' }),
        newValue: null,
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-outcome', 'unknown');
    expect(probe).toHaveAttribute('data-authenticating', 'true');
    expect(logoutCallCount()).toBe(1);

    await act(async () => {
      resolveLogout(new Response(null, { status: 204 }));
    });
    await waitFor(() => {
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-user', 'null');
      expect(probe).toHaveAttribute('data-outcome', 'confirmed');
      expect(probe).toHaveAttribute('data-authenticating', 'false');
    });
    expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();

    // 成功logoutでdirtyを消した後の外部confirmed通知は、無用な再送を発生させない。
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        oldValue: JSON.stringify({ outcome: 'unknown' }),
        newValue: null,
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-outcome', 'confirmed');
    expect(logoutCallCount()).toBe(1);
  });

  it('drains a pending guest reissue before confirming a cross-tab logout', async () => {
    localStorage.clear();
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    let resolveGuest!: (response: Response) => void;
    const guestResponse = new Promise<Response>((resolve) => {
      resolveGuest = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/guest') && init?.method === 'POST') return guestResponse;
      if (url.endsWith('/api/auth/logout') && init?.method === 'POST') return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const logoutCallCount = () => fetchMock.mock.calls.filter(([request]) => {
      const url = typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url;
      return url.endsWith('/api/auth/logout');
    }).length;
    const GuestRaceProbe: React.FC = () => {
      const { authMode, logoutOutcome } = useAuth();
      return (
        <span
          data-testid="cross-tab-guest-state"
          data-auth-mode={authMode}
          data-outcome={logoutOutcome ?? 'none'}
        />
      );
    };

    render(
      <AuthProvider clientId="test-client">
        <GuestRaceProbe />
      </AuthProvider>,
    );
    const probe = await screen.findByTestId('cross-tab-guest-state');
    expect(probe).toHaveAttribute('data-auth-mode', 'guest');
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/auth/guest', expect.objectContaining({ method: 'POST' })));

    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        newValue: JSON.stringify({ outcome: 'unknown' }),
        storageArea: window.localStorage,
      }));
    });
    expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
    expect(probe).toHaveAttribute('data-outcome', 'unknown');
    expect(logoutCallCount()).toBe(0);

    await act(async () => {
      resolveGuest(new Response(JSON.stringify({ mode: 'guest' }), { status: 200 }));
    });
    await waitFor(() => expect(logoutCallCount()).toBe(0));
    await act(async () => {
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'wordpack.logout.v1',
        oldValue: JSON.stringify({ outcome: 'unknown' }),
        newValue: null,
        storageArea: window.localStorage,
      }));
    });
    await waitFor(() => {
      expect(logoutCallCount()).toBe(1);
      expect(probe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(probe).toHaveAttribute('data-outcome', 'confirmed');
    });
    expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
    expect(fetchMock.mock.calls.map(([request]) => typeof request === 'string' ? request : request instanceof URL ? request.toString() : request.url))
      .toEqual(['/api/config', '/api/auth/guest', '/api/auth/logout']);
  });

  it('fails closed on reload when both storage writes are denied but reads are empty', async () => {
    const storagePrototype = Object.getPrototypeOf(window.localStorage) as Storage;
    const restoreBroadcastChannel = installBroadcastChannel(TestBroadcastChannel);
    TestBroadcastChannel.reset();
    let logoutStatus = 503;
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/logout')) return Promise.resolve(new Response('{}', { status: logoutStatus }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const firstRender = render(
      <AuthProvider clientId="test-client">
        <LogoutStateProbe />
      </AuthProvider>,
    );
    const firstProbe = await screen.findByTestId('logout-state');
    const setItemSpy = vi.spyOn(storagePrototype, 'setItem').mockImplementation(() => {
      throw new Error('storage writes denied');
    });

    try {
      await userEvent.setup().click(screen.getByRole('button', { name: 'ログアウト' }));
      await waitFor(() => expect(firstProbe).toHaveAttribute('data-outcome', 'failed'));
      expect(localStorage.getItem('wordpack.logout.v1')).toBeNull();
      expect(sessionStorage.getItem('wordpack.logout.v1')).toBeNull();
      firstRender.unmount();

      logoutStatus = 200;
      const reloaded = render(
        <AuthProvider clientId="test-client">
          <LogoutStateProbe />
        </AuthProvider>,
      );
      const reloadedProbe = await screen.findByTestId('logout-state');
      expect(reloadedProbe).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(reloadedProbe).toHaveAttribute('data-user', 'null');
      expect(reloadedProbe).toHaveAttribute('data-outcome', 'unknown');
      expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/google', expect.anything());
      reloaded.unmount();
    } finally {
      setItemSpy.mockRestore();
      restoreBroadcastChannel();
    }
  });

  it('does not let a late sign-in response restore state after logout starts', async () => {
    let resolveSignIn!: (response: Response) => void;
    const signInResponse = new Promise<Response>((resolve) => {
      resolveSignIn = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/google')) return signInResponse;
      if (url.endsWith('/api/auth/logout')) return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });

    localStorage.removeItem('wordpack.auth.v1');
    const RaceProbe: React.FC = () => {
      const { signIn, signOut, authMode, user } = useAuth();
      return (
        <>
          <span data-testid="race-state" data-auth-mode={authMode} data-user={user ? 'present' : 'null'} />
          <button type="button" onClick={() => void signIn('late-token').catch(() => undefined)}>サインイン</button>
          <button type="button" onClick={() => signOut()}>ログアウト</button>
        </>
      );
    };

    const user = userEvent.setup();
    render(
      <AuthProvider clientId="test-client">
        <RaceProbe />
      </AuthProvider>,
    );
    await user.click(screen.getByRole('button', { name: 'サインイン' }));
    await user.click(screen.getByRole('button', { name: 'ログアウト' }));
    expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/logout', expect.anything());
    await act(async () => {
      resolveSignIn(new Response(JSON.stringify({ user: sampleUser }), { status: 200 }));
    });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/auth/logout', expect.anything()));

    await waitFor(() => {
      expect(screen.getByTestId('race-state')).toHaveAttribute('data-auth-mode', 'anonymous');
      expect(screen.getByTestId('race-state')).toHaveAttribute('data-user', 'null');
    });
  });

  it('does not let a late guest reissue restore guest mode after logout starts', async () => {
    localStorage.clear();
    localStorage.setItem('wordpack.auth.v1', JSON.stringify({ authMode: 'guest' }));
    let resolveReissue!: (response: Response) => void;
    const reissueResponse = new Promise<Response>((resolve) => {
      resolveReissue = resolve;
    });
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
      if (url.endsWith('/api/config')) return Promise.resolve(new Response('{}', { status: 200 }));
      if (url.endsWith('/api/auth/guest')) return reissueResponse;
      if (url.endsWith('/api/auth/logout')) return Promise.resolve(new Response(null, { status: 204 }));
      return Promise.resolve(new Response('{}', { status: 404 }));
    });
    const RaceProbe: React.FC = () => {
      const { signOut, authMode, logoutOutcome } = useAuth();
      return (
        <>
          <span data-testid="guest-race-state" data-auth-mode={authMode} data-outcome={logoutOutcome ?? 'none'} />
          <button type="button" onClick={() => void signOut()}>ログアウト</button>
        </>
      );
    };

    render(
      <AuthProvider clientId="test-client">
        <RaceProbe />
      </AuthProvider>,
    );
    await screen.findByTestId('guest-race-state');
    window.dispatchEvent(new CustomEvent('auth:unauthorized', { detail: { status: 401 } }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/auth/guest', expect.objectContaining({ method: 'POST' })));
    await userEvent.setup().click(screen.getByRole('button', { name: 'ログアウト' }));
    expect(fetchMock).not.toHaveBeenCalledWith('/api/auth/logout', expect.anything());
    await act(async () => {
      resolveReissue(new Response(JSON.stringify({ mode: 'guest' }), { status: 200 }));
    });
    await waitFor(() => expect(screen.getByTestId('guest-race-state')).toHaveAttribute('data-outcome', 'confirmed'));
    await waitFor(() => expect(screen.getByTestId('guest-race-state')).toHaveAttribute('data-auth-mode', 'anonymous'));
  });
});
