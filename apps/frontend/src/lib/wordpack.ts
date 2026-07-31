import { fetchJson, ApiError } from './fetcher';
import { APP_EVENTS, dispatchAppEvent } from '../shared/events/appEvents';

export const SUPPORTED_LLM_MODELS = ['gpt-5.6-luna'] as const;
export type SupportedLlmModel = (typeof SUPPORTED_LLM_MODELS)[number];
export const DEFAULT_LLM_MODEL: SupportedLlmModel = 'gpt-5.6-luna';

export const SUPPORTED_REASONING_EFFORTS = ['none', 'low', 'medium', 'high', 'xhigh', 'max'] as const;
export type ReasoningEffort = (typeof SUPPORTED_REASONING_EFFORTS)[number];
export const DEFAULT_REASONING_EFFORT: ReasoningEffort = 'high';

export const SUPPORTED_TEXT_VERBOSITIES = ['low', 'medium', 'high'] as const;
export type TextVerbosity = (typeof SUPPORTED_TEXT_VERBOSITIES)[number];
export const DEFAULT_TEXT_VERBOSITY: TextVerbosity = 'medium';
const DEFAULT_GENERATION_JOB_TIMEOUT_MS = 25 * 60 * 1000;

export const normalizeLlmModel = (model?: string | null): SupportedLlmModel => {
  const selected = (model || '').trim();
  return SUPPORTED_LLM_MODELS.includes(selected as SupportedLlmModel)
    ? (selected as SupportedLlmModel)
    : DEFAULT_LLM_MODEL;
};

export interface ModelRequestConfig {
  model?: string;
  reasoningEffort?: ReasoningEffort;
  textVerbosity?: TextVerbosity;
}

export const composeModelRequestFields = ({
  model,
  reasoningEffort,
  textVerbosity,
}: ModelRequestConfig): Record<string, unknown> => {
  const normalizedModel = normalizeLlmModel(model || DEFAULT_LLM_MODEL);
  return {
    model: normalizedModel,
    reasoning: { effort: reasoningEffort || DEFAULT_REASONING_EFFORT },
    text: { verbosity: textVerbosity || DEFAULT_TEXT_VERBOSITY },
  };
};

export interface RegenerateSettings {
  pronunciationEnabled: boolean;
  regenerateScope: 'all' | 'examples' | 'collocations';
  requestTimeoutMs: number;
  generationRequestTimeoutMs?: number;
  reasoningEffort?: ReasoningEffort;
  textVerbosity?: TextVerbosity;
}

export interface NotificationsAdapter {
  add: (input: { title: string; message?: string; status?: 'progress' | 'success' | 'error'; id?: string; model?: string; category?: string; wordPackId?: string | null; lemma?: string | null; jobId?: string | null; pollingOwner?: 'foreground' | null }) => string;
  update: (id: string, patch: { title?: string; message?: string; status?: 'progress' | 'success' | 'error'; model?: string; category?: string; wordPackId?: string | null; lemma?: string | null; jobId?: string | null; pollingOwner?: 'foreground' | null }) => void;
}

export interface RegenerateWordPackMessages {
  // Body text shown while processing (beneath the title)
  progress?: string; // Example: "WordPackを再生成しています"
  // Body text shown on success (beneath the title)
  success?: string; // Example: 成功時に表示するメッセージ
  // Body text shown on failure (beneath the title). If omitted, error.message (if ApiError) is used
  failure?: string; // Example: 失敗時に表示するメッセージ
}

export async function regenerateWordPackRequest(params: {
  apiBase: string;
  wordPackId: string;
  settings: RegenerateSettings;
  model?: string;
  lemma?: string;
  notify: NotificationsAdapter;
  abortSignal?: AbortSignal;
  messages?: RegenerateWordPackMessages;
}): Promise<void> {
  const { apiBase, wordPackId, settings, model, lemma = 'WordPack', notify, abortSignal, messages } = params;

  const notifId = notify.add({
    title: `【${lemma}】の生成処理中...`,
    message: messages?.progress || '処理を実行しています（LLM応答の受信と解析を待機中）',
    status: 'progress',
    model: model || undefined,
    wordPackId,
    lemma,
  });
  let acceptedJobId: string | null = null;
  let confirmedJobFailure = false;

  try {
    // Firebase Hosting / CDN 経路の 60s 制限を回避するため、再生成は非同期ジョブを起動してポーリングする。
    const job = await enqueueRegenerateWordPack({
      apiBase,
      wordPackId,
      settings,
      model,
      lemma,
      abortSignal,
    });
    acceptedJobId = job.job_id;

    notify.update(notifId, { jobId: job.job_id, model: model || undefined, wordPackId, lemma, pollingOwner: 'foreground' });

    let latest = job;
    const startedAt = Date.now();
    // 目的: Hosting/CDN 経由でも完了まで「待てる」ようにする。
    // 1回の状態取得は通常API上限を使い、ジョブ全体は生成専用上限まで待つ。
    const deadlineMs = startedAt
      + (settings.generationRequestTimeoutMs ?? DEFAULT_GENERATION_JOB_TIMEOUT_MS);
    while (Date.now() < deadlineMs) {
      if (abortSignal?.aborted) break;
      if (latest.status === 'succeeded' || latest.status === 'failed') break;
      // 1回のリクエストは短く、60s を跨がないようにする
      const remainingMs = deadlineMs - Date.now();
      await new Promise((r) => setTimeout(r, Math.min(1500, remainingMs)));
      latest = await fetchRegenerateJobStatus({
        apiBase,
        wordPackId,
        jobId: job.job_id,
        abortSignal,
        timeoutMs: Math.min(settings.requestTimeoutMs, 30000),
      });
    }

    if (latest.status === 'failed') {
      const errMsg = latest.error || messages?.failure || '処理に失敗しました';
      notify.update(notifId, { title: `【${lemma}】の生成失敗`, status: 'error', message: errMsg, model: model || undefined, wordPackId, lemma, jobId: job.job_id, pollingOwner: null });
      confirmedJobFailure = true;
      throw new ApiError(errMsg, 502);
    }
    if (latest.status !== 'succeeded') {
      notify.update(notifId, {
        title: `【${lemma}】の生成中`,
        status: 'progress',
        message: '生成はサーバーで継続中です。生成キューで完了状態を確認できます。',
        model: model || undefined,
        wordPackId,
        lemma,
        jobId: job.job_id,
        pollingOwner: null,
      });
      return;
    }

    notify.update(notifId, { title: `【${lemma}】の生成完了！`, status: 'success', message: messages?.success || '処理が完了しました', model: model || undefined, wordPackId, lemma, jobId: job.job_id, pollingOwner: null });
    dispatchAppEvent(APP_EVENTS.wordPackUpdated);
  } catch (e) {
    if (acceptedJobId && !confirmedJobFailure) {
      notify.update(notifId, {
        title: `【${lemma}】の生成中`,
        status: 'progress',
        message: 'ジョブは受理済みですが状態確認に失敗しました。生成キューが確認を再開します。',
        model: model || undefined,
        wordPackId,
        lemma,
        jobId: acceptedJobId,
        pollingOwner: null,
      });
      return;
    }
    const m = messages?.failure || (e instanceof ApiError ? e.message : '処理に失敗しました');
    notify.update(notifId, { title: `【${lemma}】の生成失敗`, status: 'error', message: m, model: model || undefined, wordPackId, lemma, jobId: acceptedJobId, pollingOwner: null });
    throw e;
  }
}

// --- Async regenerate (avoids long sync wait) ---
export interface RegenerateJob {
  job_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  result?: any;
  error?: string | null;
}

export interface GuestPublicUpdateResponse {
  word_pack_id: string;
  guest_public: boolean;
}

export async function enqueueRegenerateWordPack(params: {
  apiBase: string;
  wordPackId: string;
  settings: RegenerateSettings;
  model?: string;
  lemma?: string;
  abortSignal?: AbortSignal;
}): Promise<RegenerateJob> {
  const { apiBase, wordPackId, settings, model, lemma, abortSignal } = params;
  const body = {
    pronunciation_enabled: settings.pronunciationEnabled,
    regenerate_scope: settings.regenerateScope,
    ...composeModelRequestFields({
      model,
      reasoningEffort: settings.reasoningEffort,
      textVerbosity: settings.textVerbosity,
    }),
  };
  return fetchJson<RegenerateJob>(`${apiBase}/word/packs/${wordPackId}/regenerate/async`, {
    method: 'POST',
    body,
    signal: abortSignal,
    timeoutMs: settings.requestTimeoutMs,
  });
}

export async function fetchRegenerateJobStatus(params: {
  apiBase: string;
  wordPackId: string;
  jobId: string;
  abortSignal?: AbortSignal;
  timeoutMs: number;
}): Promise<RegenerateJob> {
  const { apiBase, wordPackId, jobId, abortSignal, timeoutMs } = params;
  return fetchJson<RegenerateJob>(`${apiBase}/word/packs/${wordPackId}/regenerate/jobs/${jobId}`, {
    method: 'GET',
    signal: abortSignal,
    timeoutMs,
  });
}

export async function updateGuestPublicFlag(params: {
  apiBase: string;
  wordPackId: string;
  guestPublic: boolean;
  timeoutMs: number;
  abortSignal?: AbortSignal;
}): Promise<GuestPublicUpdateResponse> {
  const { apiBase, wordPackId, guestPublic, timeoutMs, abortSignal } = params;
  return fetchJson<GuestPublicUpdateResponse>(`${apiBase}/word/packs/${wordPackId}/guest-public`, {
    method: 'POST',
    body: { guest_public: guestPublic },
    signal: abortSignal,
    timeoutMs,
  });
}
