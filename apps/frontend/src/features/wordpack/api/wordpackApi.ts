import { fetchJson } from '../../../shared/api/fetchJson';
import {
  composeModelRequestFields,
  regenerateWordPackRequest,
  updateGuestPublicFlag,
} from '../../../lib/wordpack';
import type { WordPack, WordPackListResponse } from '../types';

export { composeModelRequestFields, regenerateWordPackRequest, updateGuestPublicFlag };

export const fetchWordPack = (
  apiBase: string,
  wordPackId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPack> => (
  fetchJson<WordPack>(`${apiBase}/word/packs/${wordPackId}`, options)
);

export const fetchWordPackList = (
  apiBase: string,
  options?: { limit?: number; offset?: number; signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPackListResponse> => {
  const limit = options?.limit ?? 200;
  const offset = options?.offset ?? 0;
  return fetchJson<WordPackListResponse>(`${apiBase}/word/packs?limit=${limit}&offset=${offset}`, {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  });
};

export const createEmptyWordPackRequest = (
  apiBase: string,
  lemma: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<{ id: string }> => (
  fetchJson<{ id: string }>(`${apiBase}/word/packs`, {
    method: 'POST',
    body: { lemma },
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  })
);

export const deleteWordPackRequest = (
  apiBase: string,
  wordPackId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<unknown> => (
  fetchJson(`${apiBase}/word/packs/${wordPackId}`, {
    method: 'DELETE',
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  })
);

export const generateWordPackRequest = (
  apiBase: string,
  body: Record<string, unknown>,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPack> => (
  fetchJson<WordPack>(`${apiBase}/word/pack`, {
    method: 'POST',
    body,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  })
);

export const updateGuestPublicRequest = updateGuestPublicFlag;
