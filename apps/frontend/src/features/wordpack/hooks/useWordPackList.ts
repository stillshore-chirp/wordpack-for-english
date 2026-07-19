import { useCallback, useEffect, useRef, useState } from 'react';
import { useSettings } from '../../../SettingsContext';
import { ApiError } from '../../../shared/api/ApiError';
import { APP_EVENTS } from '../../../shared/events/appEvents';
import { fetchWordPackList } from '../api';
import type { WordPackListItem } from '../types';

export type WordPackListMessage = { kind: 'status' | 'alert'; text: string } | null;

interface UseWordPackListOptions {
  limit?: number;
}

interface UseWordPackListResult {
  loading: boolean;
  message: WordPackListMessage;
  total: number;
  wordPacks: WordPackListItem[];
  reload: () => Promise<void>;
  applyStudyProgress: (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => void;
}

const DEFAULT_LIMIT = 200;

export const sumExamples = (counts?: WordPackListItem['examples_count']): number => {
  if (!counts) return 0;
  return Object.values(counts).reduce((sum, count) => sum + (Number(count) || 0), 0);
};

export const normalizeWordPackListItem = (item: WordPackListItem): WordPackListItem => ({
  ...item,
  checked_only_count: item.checked_only_count ?? 0,
  learned_count: item.learned_count ?? 0,
  guest_public: item.guest_public ?? false,
  is_empty: item.is_empty ?? false,
});

export const useWordPackList = ({ limit = DEFAULT_LIMIT }: UseWordPackListOptions = {}): UseWordPackListResult => {
  const { settings } = useSettings();
  const { apiBase, requestTimeoutMs } = settings;
  const abortRef = useRef<AbortController | null>(null);
  const [wordPacks, setWordPacks] = useState<WordPackListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<WordPackListMessage>(null);

  const reload = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setMessage(null);
    try {
      const res = await fetchWordPackList(apiBase, {
        limit,
        offset: 0,
        signal: controller.signal,
        timeoutMs: requestTimeoutMs,
      });
      setWordPacks(res.items.map(normalizeWordPackListItem));
      setTotal(res.total);
    } catch (error) {
      if (controller.signal.aborted) return;
      const text = error instanceof ApiError ? error.message : 'WordPack一覧の読み込みに失敗しました';
      setMessage({ kind: 'alert', text });
    } finally {
      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }, [apiBase, limit, requestTimeoutMs]);

  const applyStudyProgress = useCallback(
    (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => {
      if (!payload.wordPackId) return;
      setWordPacks((prev) =>
        prev.map((wp) =>
          wp.id === payload.wordPackId
            ? {
                ...wp,
                checked_only_count: payload.checked_only_count,
                learned_count: payload.learned_count,
              }
            : wp,
        ),
      );
    },
    [],
  );

  useEffect(() => {
    void reload();
    return () => abortRef.current?.abort();
  }, [reload]);

  useEffect(() => {
    const onUpdated = () => {
      void reload();
    };
    window.addEventListener(APP_EVENTS.wordPackUpdated, onUpdated as EventListener);
    return () => window.removeEventListener(APP_EVENTS.wordPackUpdated, onUpdated as EventListener);
  }, [reload]);

  return { loading, message, total, wordPacks, reload, applyStudyProgress };
};
