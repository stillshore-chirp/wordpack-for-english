import { fetchJson } from '../../shared/api/fetchJson';
import type {
  Quiz,
  QuizAttemptRequest,
  QuizAttemptResponse,
  QuizGenerateRequest,
  QuizGenerationJobResponse,
  QuizListResponse,
} from './types';

export const fetchQuizList = (
  apiBase: string,
  options?: { limit?: number; offset?: number; signal?: AbortSignal; timeoutMs?: number },
) => {
  const limit = options?.limit ?? 50;
  const offset = options?.offset ?? 0;
  return fetchJson<QuizListResponse>(`${apiBase}/quiz?limit=${limit}&offset=${offset}`, {
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  });
};

export const fetchQuiz = (
  apiBase: string,
  quizId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<Quiz>(`${apiBase}/quiz/${encodeURIComponent(quizId)}`, options);

export const createQuizGenerationJob = (
  apiBase: string,
  body: QuizGenerateRequest,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<QuizGenerationJobResponse>(`${apiBase}/quiz/generate/jobs`, {
  method: 'POST',
  body,
  signal: options?.signal,
  timeoutMs: options?.timeoutMs,
});

export const fetchQuizGenerationJob = (
  apiBase: string,
  jobId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<QuizGenerationJobResponse>(
  `${apiBase}/quiz/generate/jobs/${encodeURIComponent(jobId)}`,
  options,
);

export const submitQuizAttempt = (
  apiBase: string,
  quizId: string,
  body: QuizAttemptRequest,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<QuizAttemptResponse>(`${apiBase}/quiz/${encodeURIComponent(quizId)}/attempts`, {
  method: 'POST',
  body,
  signal: options?.signal,
  timeoutMs: options?.timeoutMs,
});

export const deleteQuiz = (
  apiBase: string,
  quizId: string,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<{ message: string }>(`${apiBase}/quiz/${encodeURIComponent(quizId)}`, {
  method: 'DELETE',
  signal: options?.signal,
  timeoutMs: options?.timeoutMs,
});

export const updateQuizGuestPublic = (
  apiBase: string,
  quizId: string,
  guestPublic: boolean,
  options?: { signal?: AbortSignal; timeoutMs?: number },
) => fetchJson<{ quiz_id: string; guest_public: boolean }>(
  `${apiBase}/quiz/${encodeURIComponent(quizId)}/guest-public`,
  {
    method: 'POST',
    body: { guest_public: guestPublic },
    signal: options?.signal,
    timeoutMs: options?.timeoutMs,
  },
);
