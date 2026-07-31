import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

export type NotificationStatus = 'progress' | 'success' | 'error';
export type NotificationJobType =
  | 'wordpack-regeneration'
  | 'article-import'
  | 'quiz-generation'
  | 'category-generate-import'
  | 'example-generation'
  | 'wordpack-generation';
export type NotificationPollingOwner = 'foreground';

export interface NotificationItem {
  id: string;
  title: string; // 表示用タイトル（例: 【lemma】の生成処理中...）
  message?: string; // 詳細（例: 新規生成 / 再生成 / 例文の追加生成など）
  status: NotificationStatus;
  createdAt: number;
  updatedAt: number;
  model?: string; // 任意: 使用モデル名（表示用）
  category?: string; // 任意: 選択カテゴリ（表示用）
  wordPackId?: string | null; // 任意: 完了カードからWordPackプレビューを開くためのID
  lemma?: string | null; // 任意: IDがない古い通知や生成直後のlookup用
  jobId?: string | null; // 任意: 非同期再生成ジョブの状態確認用
  jobType?: NotificationJobType | null; // 任意: ジョブ状態APIの判別用
  articleId?: string | null; // 任意: 文章インポート完了結果の参照用
  pollingOwner?: NotificationPollingOwner | null; // 現在の画面が能動poll中かを示す非永続状態
}

interface NotificationsContextValue {
  notifications: NotificationItem[];
  add: (input: { title: string; message?: string; status?: NotificationStatus; id?: string; model?: string; category?: string; wordPackId?: string | null; lemma?: string | null; jobId?: string | null; jobType?: NotificationJobType | null; articleId?: string | null; pollingOwner?: NotificationPollingOwner | null }) => string;
  update: (id: string, patch: Partial<Pick<NotificationItem, 'title' | 'message' | 'status' | 'model' | 'category' | 'wordPackId' | 'lemma' | 'jobId' | 'jobType' | 'articleId' | 'pollingOwner'>>) => void;
  remove: (id: string) => void;
  clearAll: () => void;
}

const NotificationsContext = createContext<NotificationsContextValue | undefined>(undefined);

const STORAGE_KEY = 'wpfe.notifications.v1';

function loadFromStorage(): NotificationItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const items = JSON.parse(raw) as NotificationItem[];
    if (!Array.isArray(items)) return [];
    return items.map(({ pollingOwner: _pollingOwner, ...item }) => item);
  } catch {
    return [];
  }
}

function saveToStorage(items: NotificationItem[]) {
  try {
    const persistedItems = items.map(({ pollingOwner: _pollingOwner, ...item }) => item);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(persistedItems));
  } catch {
    // ignore
  }
}

export const NotificationsProvider: React.FC<{ children: React.ReactNode } & { persist?: boolean }> = ({ children, persist = true }) => {
  const [notifications, setNotifications] = useState<NotificationItem[]>(() => (persist ? loadFromStorage() : []));
  const idSeq = useRef<number>(0);

  useEffect(() => {
    if (persist) saveToStorage(notifications);
  }, [notifications, persist]);

  const add: NotificationsContextValue['add'] = useCallback((input) => {
    const id = input.id || `n-${Date.now()}-${idSeq.current++}`;
    const now = Date.now();
    const item: NotificationItem = {
      id,
      title: input.title,
      message: input.message,
      status: input.status || 'progress',
      createdAt: now,
      updatedAt: now,
      model: input.model,
      category: input.category,
      wordPackId: input.wordPackId,
      lemma: input.lemma,
      jobId: input.jobId,
      jobType: input.jobType,
      articleId: input.articleId,
      pollingOwner: input.pollingOwner,
    };
    setNotifications((prev) => {
      const next = [...prev, item];
      return next;
    });
    return id;
  }, []);

  const update: NotificationsContextValue['update'] = useCallback((id, patch) => {
    setNotifications((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch, updatedAt: Date.now() } : n)));
  }, []);

  const remove: NotificationsContextValue['remove'] = useCallback((id) => {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }, []);

  const clearAll = useCallback(() => setNotifications([]), []);

  const value = useMemo<NotificationsContextValue>(() => ({ notifications, add, update, remove, clearAll }), [notifications, add, update, remove, clearAll]);

  return <NotificationsContext.Provider value={value}>{children}</NotificationsContext.Provider>;
};

export function useNotifications(): NotificationsContextValue {
  const ctx = useContext(NotificationsContext);
  if (!ctx) throw new Error('useNotifications must be used within NotificationsProvider');
  return ctx;
}
