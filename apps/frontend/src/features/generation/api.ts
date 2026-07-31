import { fetchJson } from '../../shared/api/fetchJson';

export interface GenerationJobResponse {
  job_id: string;
  job_type: 'category-generate-import' | 'example-generation';
  status: 'queued' | 'running' | 'succeeded' | 'failed';
  result?: Record<string, unknown> | null;
  error?: string | null;
}

interface RequestOptions {
  signal?: AbortSignal;
  timeoutMs?: number;
}

export const createCategoryGenerateImportJob = (
  apiBase: string,
  body: unknown,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  fetchJson<GenerationJobResponse>(`${apiBase}/article/generate_and_import/jobs`, {
    method: 'POST',
    body,
    ...options,
  })
);

export const fetchCategoryGenerateImportJob = (
  apiBase: string,
  jobId: string,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  fetchJson<GenerationJobResponse>(
    `${apiBase}/article/generate_and_import/jobs/${encodeURIComponent(jobId)}`,
    options,
  )
);

export const createExampleGenerationJob = (
  apiBase: string,
  wordPackId: string,
  category: string,
  body: unknown,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  fetchJson<GenerationJobResponse>(
    `${apiBase}/word/packs/${encodeURIComponent(wordPackId)}/examples/${encodeURIComponent(category)}/generate/jobs`,
    { method: 'POST', body, ...options },
  )
);

export const fetchExampleGenerationJob = (
  apiBase: string,
  wordPackId: string,
  category: string,
  jobId: string,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  fetchJson<GenerationJobResponse>(
    `${apiBase}/word/packs/${encodeURIComponent(wordPackId)}/examples/${encodeURIComponent(category)}/generate/jobs/${encodeURIComponent(jobId)}`,
    options,
  )
);
