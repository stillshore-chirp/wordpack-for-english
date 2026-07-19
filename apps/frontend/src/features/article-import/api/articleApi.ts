import { fetchJson } from '../../../shared/api/fetchJson';
import type { ArticleDetailData } from '../../../components/ArticleDetailModal';

export type ArticleDetailResponse = ArticleDetailData;

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
