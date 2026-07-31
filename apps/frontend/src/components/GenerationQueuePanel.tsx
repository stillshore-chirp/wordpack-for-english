import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNotifications, type NotificationItem } from '../NotificationsContext';
import {
  DEFAULT_GENERATION_REQUEST_TIMEOUT_MS,
  DEFAULT_REQUEST_TIMEOUT_MS,
  useOptionalSettings,
} from '../SettingsContext';
import { ApiError, fetchJson } from '../lib/fetcher';
import { DEFAULT_LLM_MODEL } from '../lib/wordpack';
import { fetchArticleImportJob } from '../features/article-import/api/articleApi';
import { WordPackPreviewModal } from './WordPackPreviewModal';
import type { WordPackListItem } from '../features/wordpack/types';

interface LemmaLookupResponse {
  found: boolean;
  id?: string | null;
  lemma?: string | null;
  sense_title?: string | null;
}

interface RegenerateJobResponse {
  job_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed';
  result?: { lemma?: string | null } | null;
  error?: string | null;
}

interface QueuePreviewMeta {
  id: string;
  lemma: string;
  senseTitle?: string | null;
}

type PreviewMessage = { kind: 'status' | 'alert'; text: string } | null;

const formatElapsed = (ms: number): string => {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const extractLemma = (title: string): string => {
  const match = title.match(/【(.+?)】/);
  if (match?.[1]) return match[1];
  return title.replace(/の生成(処理中|完了|失敗).*$/, '').trim() || 'WordPack';
};

const notificationStatusLabel = (status: NotificationItem['status']): string => (
  status === 'progress' ? '生成中' : status === 'success' ? '完了' : '失敗'
);

const buildLiveMessage = (item: NotificationItem): string => {
  const lemma = item.lemma?.trim() || extractLemma(item.title);
  const statusLabel = notificationStatusLabel(item.status);
  return `${lemma} の生成状態は${statusLabel}です${item.message ? `。${item.message}` : ''}`;
};

const bracketLemmaPattern = /【(.+?)】/;
const STALE_PROGRESS_RECONCILE_MS = 20 * 60 * 1000;
const PERSISTED_JOB_POLL_INTERVAL_MS = 5000;

const resolvePreviewLemma = (item: NotificationItem): string => {
  const storedLemma = item.lemma?.trim();
  if (storedLemma) return storedLemma;
  const match = item.title.match(bracketLemmaPattern);
  if (match?.[1]) return match[1].trim();
  return '';
};

const canOpenWordPackPreview = (item: NotificationItem): boolean => (
  item.jobType !== 'article-import'
  && item.status === 'success'
  && Boolean(item.wordPackId || resolvePreviewLemma(item))
);

const findLatestNotification = (items: NotificationItem[]): NotificationItem | null => (
  items.reduce<NotificationItem | null>((current, item) => {
    if (!current) return item;
    return item.updatedAt > current.updatedAt ? item : current;
  }, null)
);

const buildUpdateKey = (item: NotificationItem | null): string => (
  item ? `${item.id}:${item.status}:${item.updatedAt}` : 'empty'
);

const QueueItem: React.FC<{
  item: NotificationItem;
  nowMs: number;
  onRemove: (id: string) => void;
  isUpdated: boolean;
  isResolvingPreview: boolean;
  onOpenPreview: (item: NotificationItem) => void;
}> = ({
  item,
  nowMs,
  onRemove,
  isUpdated,
  isResolvingPreview,
  onOpenPreview,
}) => {
  const elapsedMs = item.status === 'progress' ? nowMs - item.createdAt : item.updatedAt - item.createdAt;
  const lemma = resolvePreviewLemma(item) || extractLemma(item.title);
  const statusLabel = notificationStatusLabel(item.status);
  const progressValue = item.status === 'progress' ? 68 : item.status === 'success' ? 100 : 100;
  const canOpenPreview = canOpenWordPackPreview(item);
  const className = [
    'generation-queue-item',
    `is-${item.status}`,
    canOpenPreview ? 'generation-queue-item--preview' : '',
    isUpdated ? 'is-updated' : '',
    isResolvingPreview ? 'is-resolving' : '',
  ].filter(Boolean).join(' ');
  const contents = (
    <>
      <div className="generation-queue-item__status" aria-hidden="true">
        {item.status === 'progress' ? <span className="generation-queue-spinner" /> : item.status === 'success' ? '✓' : '!'}
      </div>
      <div className="generation-queue-item__body">
        <div className="generation-queue-item__heading">
          <strong>{lemma}</strong>
          <span>{statusLabel}</span>
        </div>
        {item.status !== 'success' ? (
          <p>{item.message || (item.status === 'progress' ? 'LLM応答を待機しています' : '生成履歴に保存されました')}</p>
        ) : null}
        <div className="generation-queue-item__meta">
          <span>{item.category ? `${item.category}: ` : ''}{item.model || DEFAULT_LLM_MODEL}</span>
          <span>{item.status === 'progress' ? `経過 ${formatElapsed(elapsedMs)}` : `${formatElapsed(elapsedMs)}前後`}</span>
        </div>
        {item.status === 'progress' ? (
          <div
            className="generation-queue-progress"
            role="progressbar"
            aria-label={`${lemma} の生成進行状況`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={progressValue}
          >
            <span style={{ width: `${progressValue}%` }} />
          </div>
        ) : null}
        {item.status === 'progress' ? (
          <button type="button" className="generation-queue-item__remove" onClick={() => onRemove(item.id)}>
            キューから隠す
          </button>
        ) : null}
      </div>
    </>
  );

  if (canOpenPreview) {
    return (
      <button
        type="button"
        className={className}
        onClick={() => onOpenPreview(item)}
        disabled={isResolvingPreview}
        aria-busy={isResolvingPreview ? true : undefined}
        aria-label={`${lemma} の生成結果プレビューを開く`}
      >
        {contents}
      </button>
    );
  }

  return <article className={className}>{contents}</article>;
};

export const GenerationQueuePanel: React.FC = () => {
  const { notifications, clearAll, remove, update } = useNotifications();
  const settingsContext = useOptionalSettings();
  const apiBase = settingsContext?.settings.apiBase ?? '/api';
  const requestTimeoutMs = settingsContext?.settings.requestTimeoutMs ?? DEFAULT_REQUEST_TIMEOUT_MS;
  const generationRequestTimeoutMs = settingsContext?.settings.generationRequestTimeoutMs
    ?? DEFAULT_GENERATION_REQUEST_TIMEOUT_MS;
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [liveMessage, setLiveMessage] = useState('');
  const [updatedItemKeys, setUpdatedItemKeys] = useState<Record<string, string>>({});
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewWordPackId, setPreviewWordPackId] = useState<string | null>(null);
  const [previewMeta, setPreviewMeta] = useState<QueuePreviewMeta | null>(null);
  const [previewMessage, setPreviewMessage] = useState<PreviewMessage>(null);
  const [resolvingPreviewItemId, setResolvingPreviewItemId] = useState<string | null>(null);
  const lastAnnouncementKeyRef = useRef<string>(buildUpdateKey(findLatestNotification(notifications)));
  const updateTimersRef = useRef<Record<string, number>>({});
  const reconciliationRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => (
    () => {
      Object.values(updateTimersRef.current).forEach((timer) => window.clearTimeout(timer));
    }
  ), []);

  const { progressItems, doneItems } = useMemo(() => {
    const progress = notifications.filter((item) => item.status === 'progress');
    const done = notifications
      .filter((item) => item.status !== 'progress')
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 3);
    return { progressItems: progress, doneItems: done };
  }, [notifications]);

  useEffect(() => {
    progressItems.forEach((item) => {
      if (!item.jobId) return;
      const lastCheckedAt = reconciliationRef.current.get(item.id) ?? 0;
      const notificationWasRecentlyUpdated = nowMs - item.updatedAt
        < PERSISTED_JOB_POLL_INTERVAL_MS;
      if (
        lastCheckedAt > 0
        && nowMs - lastCheckedAt < PERSISTED_JOB_POLL_INTERVAL_MS
      ) return;
      if (lastCheckedAt === 0 && notificationWasRecentlyUpdated) return;
      const staleAfterMs = Math.max(
        STALE_PROGRESS_RECONCILE_MS,
        generationRequestTimeoutMs + 60 * 1000,
      );
      const isStale = nowMs - item.createdAt >= staleAfterMs;
      const lemma = resolvePreviewLemma(item) || extractLemma(item.title);
      const wordPackId = item.wordPackId?.trim() || '';
      reconciliationRef.current.set(item.id, nowMs);

      const reconcile = async () => {
        if (item.jobType === 'article-import') {
          try {
            const job = await fetchArticleImportJob(apiBase, item.jobId as string, {
              timeoutMs: requestTimeoutMs,
            });
            if (job.status === 'succeeded' && job.article_id) {
              update(item.id, {
                title: '文章インポート完了',
                status: 'success',
                message: '保存済み記事を確認しました',
                jobId: item.jobId,
                jobType: 'article-import',
                articleId: job.article_id,
              });
              return;
            }
            if (job.status !== 'failed' && !isStale) return;
            const message = job.status === 'failed'
              ? (job.error || '文章インポートジョブが失敗しました。必要ならもう一度実行してください。')
              : '文章インポートが長時間完了していません。記事一覧を確認するか、時間をおいて再試行してください。';
            update(item.id, {
              title: '文章インポートの状態を確認できません',
              status: 'error',
              message,
              jobId: item.jobId,
              jobType: 'article-import',
            });
          } catch {
            if (!isStale) return;
            update(item.id, {
              title: '文章インポートの状態を確認できません',
              status: 'error',
              message: '文章インポートジョブの状態を確認できませんでした。記事一覧を確認するか、必要ならもう一度実行してください。',
              jobId: item.jobId,
              jobType: 'article-import',
            });
          }
          return;
        }
        if (!wordPackId) {
          update(item.id, {
            title: `【${lemma || 'WordPack'}】の生成状態を確認できません`,
            status: 'error',
            message: 'WordPack IDが保存されていないため、完了状態を確認できません。保存済みWordPackを一覧で確認するか、必要ならもう一度生成してください。',
            wordPackId: item.wordPackId,
            lemma,
          });
          return;
        }
        try {
          const job = await fetchJson<RegenerateJobResponse>(
            `${apiBase}/word/packs/${wordPackId}/regenerate/jobs/${item.jobId}`,
            { timeoutMs: requestTimeoutMs },
          );
          if (job.status === 'succeeded' && job.result) {
            const resolvedLemma = job.result.lemma?.trim() || lemma;
            update(item.id, {
              title: `【${resolvedLemma || 'WordPack'}】の生成完了！`,
              status: 'success',
              message: '保存済みWordPackを確認しました',
              wordPackId,
              lemma: resolvedLemma || lemma,
              jobId: item.jobId,
            });
            return;
          }
          if (job.status !== 'failed' && !isStale) return;
          const message = job.status === 'failed'
            ? (job.error || '再生成ジョブが失敗しました。必要ならもう一度生成してください。')
            : '再生成が長時間完了していません。保存済みWordPackを一覧で確認するか、時間をおいて再試行してください。';
          update(item.id, {
            title: `【${lemma || 'WordPack'}】の生成状態を確認できません`,
            status: 'error',
            message,
            wordPackId,
            lemma,
            jobId: item.jobId,
          });
        } catch {
          if (!isStale) return;
          update(item.id, {
            title: `【${lemma || 'WordPack'}】の生成状態を確認できません`,
            status: 'error',
            message: '再生成ジョブの状態を確認できませんでした。保存済みWordPackを一覧で確認するか、必要ならもう一度生成してください。',
            wordPackId: item.wordPackId,
            lemma,
            jobId: item.jobId,
          });
        }
      };
      void reconcile();
    });
  }, [
    apiBase,
    generationRequestTimeoutMs,
    nowMs,
    progressItems,
    requestTimeoutMs,
    update,
  ]);

  useEffect(() => {
    const latest = findLatestNotification(notifications);
    const nextKey = buildUpdateKey(latest);
    if (lastAnnouncementKeyRef.current === nextKey) return;
    lastAnnouncementKeyRef.current = nextKey;
    setLiveMessage(latest ? buildLiveMessage(latest) : '生成キューを空にしました。');
    if (!latest || (latest.status !== 'progress' && latest.status !== 'success')) return;
    const pulseKey = `${latest.status}:${latest.updatedAt}`;
    setUpdatedItemKeys((prev) => ({ ...prev, [latest.id]: pulseKey }));
    const existingTimer = updateTimersRef.current[latest.id];
    if (existingTimer) {
      window.clearTimeout(existingTimer);
    }
    updateTimersRef.current[latest.id] = window.setTimeout(() => {
      setUpdatedItemKeys((prev) => {
        if (prev[latest.id] !== pulseKey) return prev;
        const next = { ...prev };
        delete next[latest.id];
        return next;
      });
      delete updateTimersRef.current[latest.id];
    }, 2000);
  }, [notifications]);

  const previewWordPacks = useMemo<WordPackListItem[]>(() => {
    if (!previewMeta) return [];
    return [{
      id: previewMeta.id,
      lemma: previewMeta.lemma,
      sense_title: previewMeta.senseTitle ?? undefined,
      created_at: '',
      updated_at: '',
      checked_only_count: 0,
      learned_count: 0,
    }];
  }, [previewMeta]);

  const openPreview = useCallback(async (item: NotificationItem) => {
    if (!canOpenWordPackPreview(item)) return;
    const fallbackLemma = resolvePreviewLemma(item) || extractLemma(item.title);
    let wordPackId = item.wordPackId?.trim() || '';
    let lemma = fallbackLemma;
    let senseTitle: string | null | undefined;

    setPreviewMessage({ kind: 'status', text: `${lemma} の保存済みWordPackを確認しています。` });
    setResolvingPreviewItemId(item.id);
    try {
      if (!wordPackId) {
        const lookup = await fetchJson<LemmaLookupResponse>(
          `${apiBase}/word/lemma/${encodeURIComponent(lemma)}`,
          { timeoutMs: requestTimeoutMs },
        );
        if (!lookup.found || !lookup.id) {
          setPreviewMessage({ kind: 'alert', text: `${lemma} の保存済みWordPackが見つからないため、プレビューを開けません。Lexiconの検索から開いてください。` });
          return;
        }
        wordPackId = lookup.id;
        lemma = lookup.lemma?.trim() || lemma;
        senseTitle = lookup.sense_title;
      }
      setPreviewMeta({ id: wordPackId, lemma: lemma || 'WordPack', senseTitle });
      setPreviewWordPackId(wordPackId);
      setPreviewOpen(true);
      setPreviewMessage(null);
    } catch (error) {
      const message = error instanceof ApiError ? error.message : '保存済みWordPackの確認に失敗しました';
      setPreviewMessage({ kind: 'alert', text: `プレビューを開けませんでした。${message}` });
    } finally {
      setResolvingPreviewItemId(null);
    }
  }, [apiBase, requestTimeoutMs]);

  return (
    <section className="generation-queue-panel" aria-label="生成キュー">
      <p className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {liveMessage}
      </p>
      <div className="generation-queue-panel__header">
        <h2>生成キュー</h2>
        <span className="generation-queue-count" aria-label={`生成履歴 ${notifications.length}件`}>
          {notifications.length}
        </span>
      </div>
      {previewMessage ? (
        <p
          className={`generation-queue-preview-message is-${previewMessage.kind}`}
          role={previewMessage.kind === 'alert' ? 'alert' : 'status'}
        >
          {previewMessage.text}
        </p>
      ) : null}

      <div className="generation-queue-section">
        <div className="generation-queue-section__header">
          <h3>進行中</h3>
          <span>{progressItems.length}</span>
          <b aria-hidden="true">⌃</b>
        </div>
        {progressItems.length ? (
          <div className="generation-queue-list">
            {progressItems.map((item) => (
              <QueueItem
                key={item.id}
                item={item}
                nowMs={nowMs}
                onRemove={remove}
                isUpdated={Boolean(updatedItemKeys[item.id])}
                isResolvingPreview={resolvingPreviewItemId === item.id}
                onOpenPreview={openPreview}
              />
            ))}
          </div>
        ) : (
          <p className="generation-queue-empty">今は生成待ちのWordPackはありません。</p>
        )}
      </div>

      <div className="generation-queue-section">
        <div className="generation-queue-section__header">
          <h3>完了</h3>
          <span>{doneItems.length}</span>
          <b aria-hidden="true">⌄</b>
        </div>
        {doneItems.length ? (
          <div className="generation-queue-list">
            {doneItems.map((item) => (
              <QueueItem
                key={item.id}
                item={item}
                nowMs={nowMs}
                onRemove={remove}
                isUpdated={Boolean(updatedItemKeys[item.id])}
                isResolvingPreview={resolvingPreviewItemId === item.id}
                onOpenPreview={openPreview}
              />
            ))}
          </div>
        ) : (
          <p className="generation-queue-empty">完了した生成はここに残ります。</p>
        )}
      </div>

      {notifications.length ? (
        <button type="button" className="generation-queue-history-button" onClick={clearAll}>
          すべての履歴を消去
        </button>
      ) : null}
      <WordPackPreviewModal
        isOpen={previewOpen}
        onClose={() => setPreviewOpen(false)}
        wordPackId={previewWordPackId}
        wordPacks={previewWordPacks}
        onWordPackUpdated={() => undefined}
      />
    </section>
  );
};
