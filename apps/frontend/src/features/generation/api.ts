import { fetchJson } from '../../shared/api/fetchJson';
import { submitIdempotentJob } from '../../shared/api/submitIdempotentJob';

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
  body: Record<string, unknown>,
  clientJobId: string,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  submitIdempotentJob(
    () => fetchJson<GenerationJobResponse>(`${apiBase}/article/generate_and_import/jobs`, {
      method: 'POST',
      body: { ...body, client_job_id: clientJobId },
      ...options,
    }),
    () => !options?.signal?.aborted,
  )
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
  body: Record<string, unknown>,
  clientJobId: string,
  options?: RequestOptions,
): Promise<GenerationJobResponse> => (
  submitIdempotentJob(
    () => fetchJson<GenerationJobResponse>(
      `${apiBase}/word/packs/${encodeURIComponent(wordPackId)}/examples/${encodeURIComponent(category)}/generate/jobs`,
      { method: 'POST', body: { ...body, client_job_id: clientJobId }, ...options },
    ),
    () => !options?.signal?.aborted,
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
