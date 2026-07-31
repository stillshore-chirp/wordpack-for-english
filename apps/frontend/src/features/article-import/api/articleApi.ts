import { fetchJson } from '../../../shared/api/fetchJson';
import type { ArticleDetailData } from '../../../components/ArticleDetailModal';

export type ArticleDetailResponse = ArticleDetailData;

export interface ArticleImportJobResponse {
  job_id: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  article_id?: string | null;
  error?: string | null;
}

export const createArticleImportJob = (
  apiBase: string,
  body: unknown,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<ArticleImportJobResponse> => (
  fetchJson<ArticleImportJobResponse>(`${apiBase}/article/import/jobs`, {
    method: 'POST',
    body,
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  })
);

export const fetchArticleImportJob = (
  apiBase: string,
  jobId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<ArticleImportJobResponse> => (
  fetchJson<ArticleImportJobResponse>(
    `${apiBase}/article/import/jobs/${encodeURIComponent(jobId)}`,
    options,
  )
);

export const fetchArticleDetail = (
  apiBase: string,
  articleId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
): Promise<ArticleDetailResponse> => (
  fetchJson<ArticleDetailResponse>(`${apiBase}/article/${articleId}`, options)
);

export const deleteWordPackFromArticle = (
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
