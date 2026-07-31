import { useCallback, useEffect, useRef, useState } from 'react';
import { useNotifications } from '../NotificationsContext';
import {
  DEFAULT_GENERATION_REQUEST_TIMEOUT_MS,
  useSettings,
} from '../SettingsContext';
import { ApiError, fetchJson } from '../lib/fetcher';
import { validateLemmaInput } from '../lib/lemmaValidation';
import { APP_EVENTS, dispatchAppEvent } from '../shared/events/appEvents';
import {
  composeModelRequestFields,
  createWordPackGenerationJob,
  enqueueRegenerateWordPack,
  fetchRegenerateJobStatus,
  fetchWordPackGenerationJob,
  updateGuestPublicFlag,
  type WordPackGenerationJob,
} from '../features/wordpack/api';
export type { ExampleItem, Examples, Pronunciation, Sense, WordPack } from '../features/wordpack/types';
import type { Examples, WordPack } from '../features/wordpack/types';

export type WordPackMessage = { kind: 'status' | 'alert'; text: string } | null;

interface UseWordPackOptions {
  model: string;
  onWordPackGenerated?: (wordPackId: string | null) => void;
  onStudyProgressRecorded?: (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => void;
}

interface AiMeta {
  model?: string | null;
  params?: string | null;
}

interface GeneratedWordPackResult {
  wordPack: WordPack;
  wordPackId: string | null;
}

const pollWordPackGenerationJob = async ({
  apiBase,
  initialJob,
  deadlineMs,
  requestTimeoutMs,
  signal,
}: {
  apiBase: string;
  initialJob: WordPackGenerationJob;
  deadlineMs: number;
  requestTimeoutMs: number;
  signal?: AbortSignal;
}): Promise<WordPackGenerationJob> => {
  let job = initialJob;
  while (
    (job.status === 'queued' || job.status === 'running')
    && Date.now() < deadlineMs
  ) {
    const remainingMs = deadlineMs - Date.now();
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, Math.min(1500, remainingMs));
    });
    job = await fetchWordPackGenerationJob(apiBase, job.job_id, {
      signal,
      timeoutMs: requestTimeoutMs,
    });
  }
  return job;
};

interface UseWordPackResult {
  aiMeta: AiMeta | null;
  currentWordPackId: string | null;
  data: WordPack | null;
  loading: boolean;
  progressUpdating: boolean;
  message: WordPackMessage;
  clearMessage: () => void;
  setStatusMessage: (next: WordPackMessage) => void;
  generateWordPack: (lemma: string) => Promise<void>;
  generateDetachedWordPack: (lemma: string) => Promise<GeneratedWordPackResult | null>;
  createEmptyWordPack: (lemma: string) => Promise<void>;
  loadWordPack: (wordPackId: string) => Promise<void>;
  regenerateWordPack: (wordPackId: string, lemma: string) => Promise<void>;
  recordStudyProgress: (kind: 'checked' | 'learned') => Promise<void>;
  updateGuestPublic: (wordPackId: string, guestPublic: boolean) => Promise<void>;
}

/**
 * WordPack取得・生成関連のAPI呼び出しと通知更新をまとめ、UIから責務を分離するカスタムフック。
 * UIは本フックが返す状態と関数を用い、描画と入力ハンドリングに専念させる。
 */
export const useWordPack = ({
  model,
  onWordPackGenerated,
  onStudyProgressRecorded,
}: UseWordPackOptions): UseWordPackResult => {
  const { settings } = useSettings();
  const { add: addNotification, update: updateNotification } = useNotifications();
  const {
    apiBase,
    generationRequestTimeoutMs,
    pronunciationEnabled,
    regenerateScope,
    requestTimeoutMs,
    reasoningEffort,
    textVerbosity,
  } = settings;
  const generationTimeoutMs = generationRequestTimeoutMs
    ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS;

  const [data, setData] = useState<WordPack | null>(null);
  const [currentWordPackId, setCurrentWordPackId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<WordPackMessage>(null);
  const [aiMeta, setAiMeta] = useState<AiMeta | null>(null);
  const [progressUpdating, setProgressUpdating] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  const clearMessage = useCallback(() => setMessage(null), []);
  const setStatusMessage = useCallback((next: WordPackMessage) => setMessage(next), []);

  const normalizeWordPack = useCallback(
    (wp: WordPack): WordPack => ({
      ...wp,
      checked_only_count: wp.checked_only_count ?? 0,
      learned_count: wp.learned_count ?? 0,
    }),
    [],
  );

  const applyModelRequestFields = useCallback(
    (base: Record<string, unknown> = {}) => ({
      ...base,
      ...composeModelRequestFields({
        model,
        reasoningEffort,
        textVerbosity,
      }),
    }),
    [model, reasoningEffort, textVerbosity],
  );

  const extractAiMeta = useCallback((pack: WordPack) => {
    try {
      const categories: (keyof Examples)[] = ['Dev', 'CS', 'LLM', 'Business', 'Common'];
      for (const category of categories) {
        const items = pack.examples?.[category] || [];
        for (const item of items) {
          if (item && item.llm_model) {
            setAiMeta({ model: item.llm_model || null, params: item.llm_params || null });
            throw new Error('meta-found');
          }
        }
      }
    } catch {
      // 例外は探索完了の合図として扱う
    }
  }, []);

  useEffect(() => {
    // Strict Mode での再マウント時に mounted 状態を復元
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const loadWordPack = useCallback(
    async (wordPackId: string) => {
      // 前のリクエストをキャンセルして Race Condition を防止
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setMessage(null);
      setData(null);
      try {
        const res = await fetchJson<WordPack>(`${apiBase}/word/packs/${wordPackId}`, {
          signal: ctrl.signal,
          timeoutMs: requestTimeoutMs,
        });
        if (!mountedRef.current) {
          return;
        }
        const normalized = normalizeWordPack(res);
        setData(normalized);
        setCurrentWordPackId(wordPackId);
        extractAiMeta(normalized);
      } catch (error) {
        if (ctrl.signal.aborted) return;
        let text = error instanceof ApiError ? error.message : 'WordPackの読み込みに失敗しました';
        if (error instanceof ApiError && error.status === 0 && /aborted|timed out/i.test(error.message)) {
          text = '読み込みがタイムアウトしました。時間をおいて再試行してください。';
        }
        setMessage({ kind: 'alert', text });
      } finally {
        setLoading(false);
      }
    },
    [apiBase, extractAiMeta, normalizeWordPack, requestTimeoutMs],
  );

  const generateWordPack = useCallback(
    async (lemma: string) => {
      const validation = validateLemmaInput(lemma);
      if (!validation.valid) {
        setMessage({ kind: 'alert', text: validation.message });
        return;
      }
      const normalizedLemma = validation.normalizedLemma;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      setLoading(true);
      setMessage(null);
      setData(null);
      const notifId = addNotification({
        title: `【${normalizedLemma}】の生成処理中...`,
        message: '新規のWordPackを生成しています（LLM応答の受信と解析を待機中）',
        status: 'progress',
        lemma: normalizedLemma,
      });
      let acceptedJobId: string | undefined;
      const clientJobId = crypto.randomUUID();
      const candidateJobId = `wordpack-generation-job:${clientJobId}`;
      let confirmedJobFailure = false;
      try {
        updateNotification(notifId, {
          message: 'WordPack生成の受付リクエストを送信しています',
          jobId: candidateJobId,
          jobType: 'wordpack-generation',
          pollingOwner: 'foreground',
        });
        const initialJob = await createWordPackGenerationJob(
          apiBase,
          applyModelRequestFields({
            lemma: normalizedLemma,
            pronunciation_enabled: pronunciationEnabled,
            regenerate_scope: regenerateScope,
          }),
          clientJobId,
          { signal: ctrl.signal, timeoutMs: requestTimeoutMs },
        );
        acceptedJobId = initialJob.job_id;
        updateNotification(notifId, {
          jobId: initialJob.job_id,
          jobType: 'wordpack-generation',
          pollingOwner: 'foreground',
        });
        const job = await pollWordPackGenerationJob({
          apiBase,
          initialJob,
          deadlineMs: Date.now() + generationTimeoutMs,
          requestTimeoutMs,
          signal: ctrl.signal,
        });
        if (job.status === 'queued' || job.status === 'running') {
          setMessage({ kind: 'status', text: 'WordPack生成は継続中です。生成キューで状態を確認できます。' });
          updateNotification(notifId, {
            title: `【${normalizedLemma}】の生成中`,
            status: 'progress',
            message: '生成はサーバーで継続中です。生成キューが状態を再確認します。',
            lemma: normalizedLemma,
            jobId: job.job_id,
            jobType: 'wordpack-generation',
            pollingOwner: null,
          });
          return;
        }
        if (job.status === 'failed' || !job.result) {
          confirmedJobFailure = true;
          throw new ApiError(job.error || 'WordPack の生成に失敗しました', 500);
        }
        const res = job.result;
        const normalized = normalizeWordPack(res);
        const generatedWordPackId = res.id?.trim() || null;
        if (mountedRef.current) {
          setData(normalized);
          setCurrentWordPackId(null);
          setMessage({ kind: 'status', text: 'WordPack を生成しました' });
          extractAiMeta(normalized);
        }
        updateNotification(notifId, {
          title: `【${res.lemma}】の生成完了！`,
          status: 'success',
          message: '新規生成が完了しました',
          wordPackId: generatedWordPackId,
          lemma: res.lemma,
          jobId: job.job_id,
          jobType: 'wordpack-generation',
          pollingOwner: null,
        });
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
        try { onWordPackGenerated?.(null); } catch {}
      } catch (error) {
        if (ctrl.signal.aborted) {
          if (acceptedJobId) updateNotification(notifId, { pollingOwner: null });
          return;
        }
        let text = error instanceof ApiError ? error.message : 'WordPack の生成に失敗しました';
        if (error instanceof ApiError && error.status === 0 && /aborted|timed out/i.test(error.message)) {
          text = 'タイムアウトしました（サーバ側で処理継続の可能性があります）。時間をおいて更新または保存済みを開いてください。';
        }
        const recoverableJobId = acceptedJobId
          ?? (error instanceof ApiError && error.status === 0 ? candidateJobId : undefined);
        if (recoverableJobId && !confirmedJobFailure) {
          const submissionConfirmed = acceptedJobId !== undefined;
          setMessage({
            kind: 'status',
            text: submissionConfirmed
              ? 'WordPack生成ジョブは受理済みです。生成キューで状態を確認できます。'
              : 'WordPack生成の送信結果を確認中です。生成キューが同じIDで受理状況を再確認します。',
          });
          updateNotification(notifId, {
            title: submissionConfirmed
              ? `【${normalizedLemma}】の生成中`
              : `【${normalizedLemma}】の受付状態を確認中`,
            status: 'progress',
            message: submissionConfirmed
              ? 'ジョブは受理済みですが状態確認に失敗しました。生成キューが確認を再開します。'
              : '送信結果が不明なため、同じジョブIDで自動確認します。',
            lemma: normalizedLemma,
            jobId: recoverableJobId,
            jobType: 'wordpack-generation',
            pollingOwner: null,
          });
          return;
        }
        setMessage({ kind: 'alert', text });
        updateNotification(notifId, {
          title: `【${normalizedLemma}】の生成失敗`,
          status: 'error',
          message: `新規生成に失敗しました（${text}）`,
          lemma: normalizedLemma,
          jobId: acceptedJobId ?? null,
          jobType: acceptedJobId ? 'wordpack-generation' : null,
          pollingOwner: null,
        });
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [addNotification, apiBase, applyModelRequestFields, extractAiMeta, generationTimeoutMs, normalizeWordPack, onWordPackGenerated, pronunciationEnabled, regenerateScope, requestTimeoutMs, updateNotification],
  );

  const generateDetachedWordPack = useCallback(
    async (lemma: string): Promise<GeneratedWordPackResult | null> => {
      const validation = validateLemmaInput(lemma);
      if (!validation.valid) {
        setMessage({ kind: 'alert', text: validation.message });
        return null;
      }
      const normalizedLemma = validation.normalizedLemma;
      const notifId = addNotification({
        title: `【${normalizedLemma}】の生成処理中...`,
        message: '新規のWordPackを生成しています（元のプレビューは保持されます）',
        status: 'progress',
        lemma: normalizedLemma,
      });
      let acceptedJobId: string | undefined;
      const clientJobId = crypto.randomUUID();
      const candidateJobId = `wordpack-generation-job:${clientJobId}`;
      let confirmedJobFailure = false;
      try {
        updateNotification(notifId, {
          message: 'WordPack生成の受付リクエストを送信しています',
          jobId: candidateJobId,
          jobType: 'wordpack-generation',
          pollingOwner: 'foreground',
        });
        const initialJob = await createWordPackGenerationJob(
          apiBase,
          applyModelRequestFields({
            lemma: normalizedLemma,
            pronunciation_enabled: pronunciationEnabled,
            regenerate_scope: regenerateScope,
          }),
          clientJobId,
          { timeoutMs: requestTimeoutMs },
        );
        acceptedJobId = initialJob.job_id;
        updateNotification(notifId, {
          jobId: initialJob.job_id,
          jobType: 'wordpack-generation',
          pollingOwner: 'foreground',
        });
        const job = await pollWordPackGenerationJob({
          apiBase,
          initialJob,
          deadlineMs: Date.now() + generationTimeoutMs,
          requestTimeoutMs,
        });
        if (job.status === 'queued' || job.status === 'running') {
          if (mountedRef.current) {
            setMessage({ kind: 'status', text: 'WordPack生成は継続中です。生成キューで状態を確認できます。' });
          }
          updateNotification(notifId, {
            title: `【${normalizedLemma}】の生成中`,
            status: 'progress',
            message: '生成はサーバーで継続中です。生成キューが状態を再確認します。',
            lemma: normalizedLemma,
            jobId: job.job_id,
            jobType: 'wordpack-generation',
            pollingOwner: null,
          });
          return null;
        }
        if (job.status === 'failed' || !job.result) {
          confirmedJobFailure = true;
          throw new ApiError(job.error || 'WordPack の生成に失敗しました', 500);
        }
        const res = job.result;
        const normalized = normalizeWordPack(res);
        const generatedWordPackId = res.id?.trim() || null;
        if (mountedRef.current) {
          setMessage({ kind: 'status', text: `${res.lemma} のWordPackを生成しました` });
        }
        updateNotification(notifId, {
          title: `【${res.lemma}】の生成完了！`,
          status: 'success',
          message: '新規生成が完了しました',
          wordPackId: generatedWordPackId,
          lemma: res.lemma,
          jobId: job.job_id,
          jobType: 'wordpack-generation',
          pollingOwner: null,
        });
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
        return { wordPack: normalized, wordPackId: generatedWordPackId };
      } catch (error) {
        let text = error instanceof ApiError ? error.message : 'WordPack の生成に失敗しました';
        if (error instanceof ApiError && error.status === 0 && /timed out/i.test(error.message)) {
          text = 'タイムアウトしました（サーバ側で処理継続の可能性があります）。時間をおいて更新または保存済みを開いてください。';
        }
        const recoverableJobId = acceptedJobId
          ?? (error instanceof ApiError && error.status === 0 ? candidateJobId : undefined);
        const submissionConfirmed = acceptedJobId !== undefined;
        if (mountedRef.current) {
          setMessage({
            kind: recoverableJobId && !confirmedJobFailure ? 'status' : 'alert',
            text: recoverableJobId && !confirmedJobFailure
              ? (
                submissionConfirmed
                  ? 'WordPack生成ジョブは受理済みです。生成キューで状態を確認できます。'
                  : 'WordPack生成の送信結果を確認中です。生成キューが同じIDで受理状況を再確認します。'
              )
              : text,
          });
        }
        if (recoverableJobId && !confirmedJobFailure) {
          updateNotification(notifId, {
            title: submissionConfirmed
              ? `【${normalizedLemma}】の生成中`
              : `【${normalizedLemma}】の受付状態を確認中`,
            status: 'progress',
            message: submissionConfirmed
              ? 'ジョブは受理済みですが状態確認に失敗しました。生成キューが確認を再開します。'
              : '送信結果が不明なため、同じジョブIDで自動確認します。',
            lemma: normalizedLemma,
            jobId: recoverableJobId,
            jobType: 'wordpack-generation',
            pollingOwner: null,
          });
          return null;
        }
        updateNotification(notifId, {
          title: `【${normalizedLemma}】の生成失敗`,
          status: 'error',
          message: `新規生成に失敗しました（${text}）`,
          lemma: normalizedLemma,
          jobId: acceptedJobId ?? null,
          jobType: acceptedJobId ? 'wordpack-generation' : null,
          pollingOwner: null,
        });
        return null;
      }
    },
    [addNotification, apiBase, applyModelRequestFields, generationTimeoutMs, normalizeWordPack, pronunciationEnabled, regenerateScope, requestTimeoutMs, updateNotification],
  );

  const createEmptyWordPack = useCallback(
    async (lemma: string) => {
      const validation = validateLemmaInput(lemma);
      if (!validation.valid) {
        setMessage({ kind: 'alert', text: validation.message });
        return;
      }
      const normalizedLemma = validation.normalizedLemma;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setMessage(null);
      const notifId = addNotification({
        title: `【${normalizedLemma}】の生成処理中...`,
        message: '空のWordPackを作成しています',
        status: 'progress',
        lemma: normalizedLemma,
      });
      try {
        const res = await fetchJson<{ id: string }>(`${apiBase}/word/packs`, {
          method: 'POST',
          body: { lemma: normalizedLemma },
          signal: ctrl.signal,
          timeoutMs: requestTimeoutMs,
        });
        setCurrentWordPackId(res.id);
        await loadWordPack(res.id);
        try { onWordPackGenerated?.(res.id); } catch {}
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
        updateNotification(notifId, { title: `【${normalizedLemma}】の生成完了！`, status: 'success', message: '詳細読み込み完了', wordPackId: res.id, lemma: normalizedLemma });
      } catch (error) {
        if (ctrl.signal.aborted) return;
        const text = error instanceof ApiError ? error.message : '空のWordPack作成に失敗しました';
        setMessage({ kind: 'alert', text });
        updateNotification(notifId, { title: `【${normalizedLemma}】の生成失敗`, status: 'error', message: `空のWordPackの作成に失敗しました（${text}）`, lemma: normalizedLemma });
      } finally {
        setLoading(false);
      }
    },
    [addNotification, apiBase, loadWordPack, onWordPackGenerated, requestTimeoutMs, updateNotification],
  );

  const recordStudyProgress = useCallback(
    async (kind: 'checked' | 'learned') => {
      if (!currentWordPackId) return;
      setProgressUpdating(true);
      try {
        const res = await fetchJson<{ checked_only_count: number; learned_count: number }>(
          `${apiBase}/word/packs/${currentWordPackId}/study-progress`,
          {
            method: 'POST',
            body: { kind },
          },
        );
        setData((prev) =>
          prev
            ? {
                ...prev,
                checked_only_count: res.checked_only_count,
                learned_count: res.learned_count,
              }
            : prev,
        );
        const detail = {
          wordPackId: currentWordPackId,
          checked_only_count: res.checked_only_count,
          learned_count: res.learned_count,
        };
        try { onStudyProgressRecorded?.(detail); } catch {}
        dispatchAppEvent(APP_EVENTS.wordPackStudyProgress, detail);
        setMessage({
          kind: 'status',
          text: kind === 'learned' ? '学習済みとして記録しました' : '確認済みとして記録しました',
        });
      } catch (error) {
        const text = error instanceof ApiError ? error.message : '学習状況の記録に失敗しました';
        setMessage({ kind: 'alert', text });
      } finally {
        setProgressUpdating(false);
      }
    },
    [apiBase, currentWordPackId, onStudyProgressRecorded],
  );

  const updateGuestPublic = useCallback(
    async (wordPackId: string, guestPublic: boolean) => {
      if (!wordPackId) return;
      const previous = data?.guest_public ?? false;
      setData((prev) => (prev ? { ...prev, guest_public: guestPublic } : prev));
      try {
        await updateGuestPublicFlag({
          apiBase,
          wordPackId,
          guestPublic,
          timeoutMs: requestTimeoutMs,
        });
        setMessage({
          kind: 'status',
          text: guestPublic ? 'ゲスト公開を有効にしました' : 'ゲスト公開を解除しました',
        });
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      } catch (error) {
        setData((prev) => (prev ? { ...prev, guest_public: previous } : prev));
        const text = error instanceof ApiError ? error.message : 'ゲスト公開の更新に失敗しました';
        setMessage({ kind: 'alert', text });
      }
    },
    [apiBase, data?.guest_public, requestTimeoutMs],
  );

  const regenerateWordPack = useCallback(
    async (wordPackId: string, lemma: string) => {
      const ctrl = new AbortController();
      setLoading(true);
      setMessage(null);
      let notifId: string | null = null;
      let acceptedJobId: string | null = null;
      try {
        notifId = addNotification({
          title: `【${lemma}】の再生成ジョブ開始`,
          message: 'バックグラウンドで再生成しています（完了までしばらくお待ちください）',
          status: 'progress',
          model: model || undefined,
          wordPackId,
          lemma,
          pollingOwner: 'foreground',
        });

        const job = await enqueueRegenerateWordPack({
          apiBase,
          wordPackId,
          settings: {
            pronunciationEnabled,
            regenerateScope,
            requestTimeoutMs,
            generationRequestTimeoutMs: generationTimeoutMs,
            reasoningEffort,
            textVerbosity,
          },
          model,
          lemma,
          abortSignal: ctrl.signal,
        });
        acceptedJobId = job.job_id;
        updateNotification(notifId, {
          jobId: job.job_id,
          model: model || undefined,
          wordPackId,
          lemma,
        });

        const pollingDeadline = Date.now() + Math.max(1000, generationTimeoutMs);
        let latest = job;
        while (Date.now() < pollingDeadline) {
          if (ctrl.signal.aborted) break;
          if (latest.status === 'succeeded' || latest.status === 'failed') break;
          const remainingMs = pollingDeadline - Date.now();
          await new Promise((resolve) => setTimeout(resolve, Math.min(1500, remainingMs)));
          latest = await fetchRegenerateJobStatus({
            apiBase,
            wordPackId,
            jobId: job.job_id,
            abortSignal: ctrl.signal,
            timeoutMs: requestTimeoutMs,
          });
        }

        if (latest.status === 'succeeded' && latest.result) {
          const normalized = normalizeWordPack(latest.result as WordPack);
          if (mountedRef.current) {
            setData(normalized);
            setCurrentWordPackId(wordPackId);
            extractAiMeta(normalized);
            setMessage({ kind: 'status', text: 'WordPackを再生成しました' });
          }
          updateNotification(notifId, {
            title: `【${lemma}】の再生成完了`,
            status: 'success',
            message: 'バックグラウンド再生成が完了しました',
            model: model || undefined,
            wordPackId,
            lemma,
            jobId: job.job_id,
            pollingOwner: null,
          });
          try { onWordPackGenerated?.(wordPackId); } catch {}
        } else if (latest.status === 'failed') {
          const errText = latest.error || '再生成が完了しませんでした（時間をおいて再試行してください）';
          if (mountedRef.current) setMessage({ kind: 'alert', text: errText });
          updateNotification(notifId, {
            title: `【${lemma}】の再生成失敗`,
            status: 'error',
            message: errText,
            model: model || undefined,
            wordPackId,
            lemma,
            jobId: job.job_id,
            pollingOwner: null,
          });
        } else {
          const progressText = '再生成はサーバーで継続中です。生成キューで完了状態を確認できます。';
          if (mountedRef.current) setMessage({ kind: 'status', text: progressText });
          updateNotification(notifId, {
            title: `【${lemma}】の再生成中`,
            status: 'progress',
            message: progressText,
            model: model || undefined,
            wordPackId,
            lemma,
            jobId: job.job_id,
            pollingOwner: null,
          });
        }
      } catch (error) {
        if (ctrl.signal.aborted) {
          if (notifId) updateNotification(notifId, { pollingOwner: null });
          return;
        }
        let text = error instanceof ApiError ? error.message : 'WordPackの再生成に失敗しました';
        if (error instanceof ApiError && error.status === 0 && /aborted|timed out/i.test(error.message)) {
          text = '再生成がタイムアウトしました（サーバ側で処理継続の可能性）。時間をおいて再試行してください。';
        }
        const followUpUnknown = Boolean(acceptedJobId);
        if (mountedRef.current) {
          setMessage({
            kind: followUpUnknown ? 'status' : 'alert',
            text: followUpUnknown
              ? '再生成ジョブは受理済みです。生成キューで完了状態を確認できます。'
              : text,
          });
        }
        if (notifId) {
          updateNotification(notifId, {
            title: followUpUnknown
              ? `【${lemma}】の再生成中`
              : `【${lemma}】の再生成状態を確認できません`,
            status: followUpUnknown ? 'progress' : 'error',
            message: followUpUnknown
              ? 'ジョブは受理済みですが状態確認に失敗しました。生成キューが確認を再開します。'
              : `${text}。保存済みWordPackを確認するか、時間をおいて再試行してください。`,
            model: model || undefined,
            wordPackId,
            lemma,
            jobId: acceptedJobId,
            pollingOwner: null,
          });
        }
      } finally {
        if (mountedRef.current) {
          setLoading(false);
        }
      }
    },
    [
      addNotification,
      apiBase,
      extractAiMeta,
      generationTimeoutMs,
      model,
      normalizeWordPack,
      onWordPackGenerated,
      pronunciationEnabled,
      regenerateScope,
      reasoningEffort,
      requestTimeoutMs,
      textVerbosity,
      updateNotification,
    ],
  );

  return {
    aiMeta,
    currentWordPackId,
    data,
    loading,
    progressUpdating,
    message,
    clearMessage,
    setStatusMessage,
    generateWordPack,
    generateDetachedWordPack,
    createEmptyWordPack,
    loadWordPack,
    regenerateWordPack,
    recordStudyProgress,
    updateGuestPublic,
  };
};
