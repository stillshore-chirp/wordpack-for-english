import { describe, expect, it, vi, afterEach } from 'vitest';
import { fetchJson } from './fetcher';

type FetchMock = ReturnType<typeof vi.fn<typeof fetch>>;

const buildJsonResponse = (payload: unknown = { ok: true }) => {
  return {
    ok: true,
    status: 200,
    headers: {
      get: vi.fn().mockReturnValue('application/json'),
    } as unknown as Headers,
    json: vi.fn().mockResolvedValue(payload),
    text: vi.fn().mockResolvedValue(''),
  };
};

const installFetchMock = (responsePayload?: unknown): FetchMock => {
  const mock = vi.fn<typeof fetch>();
  mock.mockResolvedValue(buildJsonResponse(responsePayload) as unknown as Response);
  globalThis.fetch = mock as unknown as typeof fetch;
  return mock;
};

const installErrorFetchMock = (status: number, responsePayload: unknown): FetchMock => {
  const mock = vi.fn<typeof fetch>();
  mock.mockResolvedValue({
    ok: false,
    status,
    headers: {
      get: vi.fn().mockReturnValue('application/json'),
    } as unknown as Headers,
    json: vi.fn().mockResolvedValue(responsePayload),
    text: vi.fn().mockResolvedValue(''),
  } as unknown as Response);
  globalThis.fetch = mock as unknown as typeof fetch;
  return mock;
};

describe('fetchJson credential behavior', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it('sends credentials=include by default', async () => {
    const fetchMock = installFetchMock({ ok: true });

    await fetchJson('/api/article/import');

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/article/import',
      expect.objectContaining({
        credentials: 'include',
        cache: 'no-store',
        method: 'GET',
      }),
    );
  });

  it('allows overriding credentials option', async () => {
    const fetchMock = installFetchMock({ ok: true });

    await fetchJson('/api/article/import', { credentials: 'omit' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/article/import',
      expect.objectContaining({
        credentials: 'omit',
      }),
    );
  });
});

describe('fetchJson unauthorized dispatch', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it('dispatches auth:unauthorized for session 401 responses', async () => {
    installErrorFetchMock(401, { detail: 'Not authenticated' });
    const listener = vi.fn();
    window.addEventListener('auth:unauthorized', listener);

    try {
      await expect(fetchJson('/api/protected')).rejects.toMatchObject({ status: 401 });
      expect(listener).toHaveBeenCalledTimes(1);
    } finally {
      window.removeEventListener('auth:unauthorized', listener);
    }
  });

  it('keeps LLM provider authentication failures on the current screen', async () => {
    installErrorFetchMock(401, {
      detail: {
        message: 'LLM provider authentication failed',
        reason_code: 'AUTH',
        hint: 'OPENAI_API_KEY を確認',
      },
    });
    const listener = vi.fn();
    window.addEventListener('auth:unauthorized', listener);

    try {
      await expect(fetchJson('/api/word/pack', { method: 'POST', body: { lemma: 'alpha' } }))
        .rejects.toThrow('LLM provider authentication failed');
      expect(listener).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener('auth:unauthorized', listener);
    }
  });
});

