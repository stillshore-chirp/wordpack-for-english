import { useCallback, useState } from 'react';
import { ApiError, fetchJson } from '../lib/fetcher';
import { APP_EVENTS, dispatchAppEvent } from '../shared/events/appEvents';
import {
  composeModelRequestFields,
  type ReasoningEffort,
  type TextVerbosity,
} from '../lib/wordpack';
import { Examples, WordPack, WordPackMessage } from './useWordPack';
import type { useNotifications } from '../NotificationsContext';
import {
  createArticleImportJob,
  fetchArticleImportJob,
} from '../features/article-import/api/articleApi';
import { DEFAULT_GENERATION_REQUEST_TIMEOUT_MS } from '../SettingsContext';

interface UseExampleActionsParams {
  apiBase: string;
  requestTimeoutMs: number;
  generationRequestTimeoutMs?: number;
  currentWordPackId: string | null;
  data: WordPack | null;
  model: string;
  reasoningEffort?: ReasoningEffort;
  textVerbosity?: TextVerbosity;
  setStatusMessage: (next: WordPackMessage) => void;
  loadWordPack: (wordPackId: string) => Promise<void>;
  notify: Pick<ReturnType<typeof useNotifications>, 'add' | 'update'>;
  confirmDialog: (targetLabel: string) => Promise<boolean>;
  onWordPackGenerated?: (wordPackId: string | null) => void;
}

interface UseExampleActionsResult {
  examplesLoading: boolean;
  deleteExample: (category: keyof Examples, index: number) => Promise<void>;
  generateExamples: (category: keyof Examples) => Promise<void>;
  importArticleFromExample: (category: keyof Examples, index: number) => Promise<void>;
  copyExampleText: (category: keyof Examples, index: number) => Promise<void>;
}

// 例文まわりの副作用をまとめて扱うフック。
// 境界条件として、サーバー更新系の操作は currentWordPackId が存在する（保存済み）場合のみ実行する。
export const useExampleActions = ({
  apiBase,
  requestTimeoutMs,
  generationRequestTimeoutMs,
  currentWordPackId,
  data,
  model,
  reasoningEffort,
  textVerbosity,
  setStatusMessage,
  loadWordPack,
  notify,
  confirmDialog,
  onWordPackGenerated,
}: UseExampleActionsParams): UseExampleActionsResult => {
  const [examplesLoading, setExamplesLoading] = useState(false);

  const ensureSavedWordPack = useCallback(() => {
    if (!currentWordPackId) {
      setStatusMessage({ kind: 'alert', text: '保存済みWordPackでのみ利用できます' });
      return false;
    }
    return true;
  }, [currentWordPackId, setStatusMessage]);

  const resolveErrorMessage = useCallback((error: unknown, fallback: string) => {
    if (error instanceof ApiError) return error.message;
    return fallback;
  }, []);

  const getExample = useCallback(
    (category: keyof Examples, index: number) => {
      const ex = data?.examples?.[category]?.[index];
      if (!ex || !ex.en) {
        setStatusMessage({ kind: 'alert', text: '例文が見つかりません' });
        return null;
      }
      return ex;
    },
    [data?.examples, setStatusMessage],
  );

  const buildModelRequest = useCallback(
    () =>
      composeModelRequestFields({
        model,
        reasoningEffort,
        textVerbosity,
      }),
    [model, reasoningEffort, textVerbosity],
  );

  const deleteExample = useCallback(
    async (category: keyof Examples, index: number) => {
      if (!ensureSavedWordPack()) return;
      const wordPackId = currentWordPackId;
      if (!wordPackId) return;
      const confirmed = await confirmDialog('例文');
      if (!confirmed) return;

      const ctrl = new AbortController();
      setStatusMessage(null);
      setExamplesLoading(true);
      try {
        await fetchJson(`${apiBase}/word/packs/${wordPackId}/examples/${category}/${index}`, {
          method: 'DELETE',
          signal: ctrl.signal,
          timeoutMs: requestTimeoutMs,
        });
        setStatusMessage({ kind: 'status', text: '例文を削除しました' });
        await loadWordPack(wordPackId);
      } catch (error) {
        if (ctrl.signal.aborted) return;
        const text = resolveErrorMessage(error, '例文の削除に失敗しました');
        setStatusMessage({ kind: 'alert', text });
      } finally {
        setExamplesLoading(false);
      }
    },
    [apiBase, confirmDialog, currentWordPackId, ensureSavedWordPack, loadWordPack, requestTimeoutMs, resolveErrorMessage, setStatusMessage],
  );

  const generateExamples = useCallback(
    async (category: keyof Examples) => {
      if (!ensureSavedWordPack()) return;
      const wordPackId = currentWordPackId;
      if (!wordPackId) return;
      const ctrl = new AbortController();
      const lemmaText = data?.lemma || '(unknown)';
      setStatusMessage(null);
      setExamplesLoading(true);
      const notifId = notify.add({
        title: `【${lemmaText}】の生成処理中...`,
        message: `例文（${category}）を2件追加生成しています`,
        status: 'progress',
        model,
        category,
        wordPackId,
        lemma: lemmaText,
      });
      try {
        const requestBody = buildModelRequest();
        await fetchJson(`${apiBase}/word/packs/${wordPackId}/examples/${category}/generate`, {
          method: 'POST',
          body: requestBody,
          signal: ctrl.signal,
          timeoutMs: generationRequestTimeoutMs ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS,
        });
        setStatusMessage({ kind: 'status', text: `${category} に例文を2件追加しました` });
        notify.update(notifId, { title: `【${lemmaText}】の生成完了！`, status: 'success', message: `${category} に例文を2件追加しました`, model, category, wordPackId, lemma: lemmaText });
        await loadWordPack(wordPackId);
        try { onWordPackGenerated?.(wordPackId); } catch {}
      } catch (error) {
        if (ctrl.signal.aborted) {
          notify.update(notifId, { title: `【${lemmaText}】の生成失敗`, status: 'error', message: '処理を中断しました', model, category, wordPackId, lemma: lemmaText });
          return;
        }
        const text = resolveErrorMessage(error, '例文の追加生成に失敗しました');
        setStatusMessage({ kind: 'alert', text });
        notify.update(notifId, {
          title: `【${lemmaText}】の生成失敗`,
          status: 'error',
          message: `${category} の例文追加生成に失敗しました（${text}）`,
          model,
          category,
          wordPackId,
          lemma: lemmaText,
        });
      } finally {
        setExamplesLoading(false);
      }
    },
    [apiBase, buildModelRequest, currentWordPackId, data?.lemma, ensureSavedWordPack, generationRequestTimeoutMs, loadWordPack, model, notify, onWordPackGenerated, requestTimeoutMs, resolveErrorMessage, setStatusMessage],
  );

  const importArticleFromExample = useCallback(
    async (category: keyof Examples, index: number) => {
      if (!ensureSavedWordPack()) return;
      const wordPackId = currentWordPackId;
      if (!wordPackId) return;
      const ex = getExample(category, index);
      if (!ex) return;

      const ctrl = new AbortController();
      setStatusMessage(null);
      setExamplesLoading(true);
      const lemmaText = data?.lemma || '(unknown)';
      const notifId = notify.add({
        title: `【${lemmaText}】文章インポート中...`,
        message: '当該の例文を元に記事を生成しています',
        status: 'progress',
      });
      let acceptedJobId: string | undefined;
      let confirmedJobFailure = false;

      try {
        let job = await createArticleImportJob(apiBase, { text: ex.en }, {
          signal: ctrl.signal,
          timeoutMs: requestTimeoutMs,
        });
        acceptedJobId = job.job_id;
        notify.update(notifId, {
          message: 'バックグラウンドで文章を処理しています',
          jobId: job.job_id,
          jobType: 'article-import',
        });
        const deadlineMs = Date.now()
          + (generationRequestTimeoutMs ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS);
        while (job.status === 'queued' || job.status === 'running') {
          if (Date.now() >= deadlineMs) {
            throw new ApiError(
              '文章インポートが制限時間内に完了しませんでした。生成キューから状態を確認してください。',
              0,
            );
          }
          await new Promise<void>((resolve) => window.setTimeout(resolve, 1000));
          job = await fetchArticleImportJob(apiBase, job.job_id, {
            signal: ctrl.signal,
            timeoutMs: requestTimeoutMs,
          });
          notify.update(notifId, {
            message: 'バックグラウンドで文章を処理しています',
            jobId: job.job_id,
            jobType: 'article-import',
          });
        }
        if (job.status === 'failed') {
          confirmedJobFailure = true;
          throw new ApiError(job.error || '文章インポートに失敗しました', 500);
        }
        if (!job.article_id) {
          confirmedJobFailure = true;
          throw new ApiError('文章インポート結果を確認できませんでした', 500);
        }
        notify.update(notifId, {
          title: '文章インポート完了',
          status: 'success',
          message: '記事一覧を更新しました',
          jobId: job.job_id,
          jobType: 'article-import',
          articleId: job.article_id,
        });
        dispatchAppEvent(APP_EVENTS.articleUpdated);
        setStatusMessage({ kind: 'status', text: '例文から文章インポートを実行しました' });
      } catch (error) {
        if (ctrl.signal.aborted) {
          notify.update(notifId, { title: '文章インポートを中断', status: 'error', message: '処理をキャンセルしました' });
          return;
        }
        const m = resolveErrorMessage(error, '文章インポートに失敗しました');
        if (acceptedJobId && !confirmedJobFailure) {
          setStatusMessage({
            kind: 'alert',
            text: '文章インポートはバックグラウンドで継続しています。生成キューから状態を確認してください。',
          });
          notify.update(notifId, {
            title: '文章インポートの状態を確認中',
            status: 'progress',
            message: '一時的に状態を取得できませんでした。自動で再確認します。',
            jobId: acceptedJobId,
            jobType: 'article-import',
          });
        } else {
          setStatusMessage({ kind: 'alert', text: m });
          notify.update(notifId, {
            title: '文章インポート失敗',
            status: 'error',
            message: m,
          });
        }
      } finally {
        setExamplesLoading(false);
      }
    },
    [apiBase, currentWordPackId, data?.lemma, ensureSavedWordPack, generationRequestTimeoutMs, getExample, notify, requestTimeoutMs, resolveErrorMessage, setStatusMessage],
  );

  const copyExampleText = useCallback(
    async (category: keyof Examples, index: number) => {
      const ex = getExample(category, index);
      if (!ex) return;
      try {
        const text = ex.en;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.left = '-9999px';
          document.body.appendChild(ta);
          ta.focus();
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }
        notify.add({ title: 'コピー完了', message: '例文をクリップボードにコピーしました', status: 'success' });
      } catch (error) {
        const m = resolveErrorMessage(error, 'コピーに失敗しました');
        setStatusMessage({ kind: 'alert', text: m });
      }
    },
    [getExample, notify, resolveErrorMessage, setStatusMessage],
  );

  return {
    examplesLoading,
    deleteExample,
    generateExamples,
    importArticleFromExample,
    copyExampleText,
  };
};
