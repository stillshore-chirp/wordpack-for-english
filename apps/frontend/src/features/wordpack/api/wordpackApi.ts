import { fetchJson } from '../../../shared/api/fetchJson';
import { submitIdempotentJob } from '../../../shared/api/submitIdempotentJob';
import {
  composeModelRequestFields,
  regenerateWordPackRequest,
  updateGuestPublicFlag,
} from '../../../lib/wordpack';
import type { WordPack, WordPackListResponse } from '../types';

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
  options?: WordPackListQueryOptions,
): Promise<WordPackListResponse> => {
  const limit = options?.limit ?? 200;
  const offset = options?.offset ?? 0;
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
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

export interface WordPackGenerationJob {
  job_id: string;
  job_type: 'wordpack-generation';
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  result?: WordPack | null;
  error?: string | null;
}

export const createWordPackGenerationJob = (
  apiBase: string,
  body: Record<string, unknown>,
  clientJobId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPackGenerationJob> => (
  submitIdempotentJob(
    () => fetchJson<WordPackGenerationJob>(`${apiBase}/word/pack/jobs`, {
      method: 'POST',
      body: { ...body, client_job_id: clientJobId },
      signal: options?.signal,
      timeoutMs: options?.timeoutMs,
    }),
    () => !options?.signal?.aborted,
  )
);

export const fetchWordPackGenerationJob = (
  apiBase: string,
  jobId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<WordPackGenerationJob> => (
  fetchJson<WordPackGenerationJob>(
    `${apiBase}/word/pack/jobs/${encodeURIComponent(jobId)}`,
    {
      signal: options?.signal,
      timeoutMs: options?.timeoutMs,
    },
  )
);

export const updateGuestPublicRequest = updateGuestPublicFlag;
