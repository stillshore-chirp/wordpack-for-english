import { fetchJson } from '../../../shared/api/fetchJson';
import {
  composeModelRequestFields,
  regenerateWordPackRequest,
  updateGuestPublicFlag,
} from '../../../lib/wordpack';
import type { WordPack, WordPackListResponse } from '../types';

export { composeModelRequestFields, regenerateWordPackRequest, updateGuestPublicFlag };

export interface WordPackListQueryOptions {
  limit?: number;
  offset?: number;
  search?: string;
  searchMode?: 'prefix' | 'suffix' | 'contains';
  visibility?: 'all' | 'public' | 'private';
  generation?: 'all' | 'generated' | 'not_generated';
  sortKey?: 'created_at' | 'updated_at' | 'lemma' | 'total_examples';
  sortOrder?: 'asc' | 'desc';
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const fetchWordPack = (
  apiBase: string,
  wordPackId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPack> => (
  fetchJson<WordPack>(`${apiBase}/word/packs/${wordPackId}`, options)
);

export const fetchWordPackList = (
  apiBase: string,
  options?: WordPackListQueryOptions,
): Promise<WordPackListResponse> => {
  const params = new URLSearchParams({
    limit: String(options?.limit ?? 200),
    offset: String(options?.offset ?? 0),
  });
  if (options?.search) params.set('search', options.search);
  if (options?.searchMode) params.set('search_mode', options.searchMode);
  if (options?.visibility) params.set('visibility', options.visibility);
  if (options?.generation) params.set('generation', options.generation);
  if (options?.sortKey) params.set('sort_key', options.sortKey);
  if (options?.sortOrder) params.set('sort_order', options.sortOrder);
  return fetchJson<WordPackListResponse>(`${apiBase}/word/packs?${params.toString()}`, {
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
