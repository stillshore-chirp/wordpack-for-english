import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSettings } from '../../SettingsContext';
import { ApiError } from '../../shared/api/ApiError';
import { createEmptyWordPackRequest, fetchWordPack } from '../../features/wordpack/api';
import { useWordPackList } from '../../features/wordpack/hooks/useWordPackList';
import type { WordPack } from '../../features/wordpack/types';

export const useExploreData = () => {
  const { settings } = useSettings();
  const list = useWordPackList();
  const [query, setQuery] = useState('');
  const [selectedWordPackId, setSelectedWordPackId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<WordPack | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailMessage, setDetailMessage] = useState<string | null>(null);

  const filteredWordPacks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return list.wordPacks;
    return list.wordPacks.filter((wordPack) => {
      const lemma = wordPack.lemma.toLowerCase();
      const senseTitle = (wordPack.sense_title ?? '').toLowerCase();
      return lemma.includes(normalizedQuery) || senseTitle.includes(normalizedQuery);
    });
  }, [list.wordPacks, query]);

  useEffect(() => {
    if (filteredWordPacks.length === 0) {
      setSelectedWordPackId(null);
      return;
    }
    if (!selectedWordPackId || !filteredWordPacks.some((wordPack) => wordPack.id === selectedWordPackId)) {
      setSelectedWordPackId(filteredWordPacks[0].id);
    }
  }, [filteredWordPacks, selectedWordPackId]);

  useEffect(() => {
    if (!selectedWordPackId) {
      setSelectedDetail(null);
      setDetailMessage(null);
      return undefined;
    }
    const controller = new AbortController();
    setDetailLoading(true);
    setDetailMessage(null);
    setSelectedDetail(null);
    fetchWordPack(settings.apiBase, selectedWordPackId, {
      signal: controller.signal,
      timeoutMs: settings.requestTimeoutMs,
    })
      .then((wordPack) => {
        setSelectedDetail(wordPack);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        const text = error instanceof ApiError ? error.message : 'WordPack詳細の読み込みに失敗しました';
        setDetailMessage(text);
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setDetailLoading(false);
        }
      });
    return () => controller.abort();
  }, [selectedWordPackId, settings.apiBase, settings.requestTimeoutMs]);

  const selectedWordPack = useMemo(
    () => list.wordPacks.find((wordPack) => wordPack.id === selectedWordPackId) ?? null,
    [list.wordPacks, selectedWordPackId],
  );

  const createEmptyWordPack = useCallback((lemma: string): Promise<{ id: string }> => (
    createEmptyWordPackRequest(settings.apiBase, lemma, {
      timeoutMs: settings.requestTimeoutMs,
    })
  ), [settings.apiBase, settings.requestTimeoutMs]);

  return {
    ...list,
    createEmptyWordPack,
    detailLoading,
    detailMessage,
    filteredWordPacks,
    query,
    selectedDetail,
    selectedWordPack,
    selectedWordPackId,
    setQuery,
    setSelectedWordPackId,
  };
};
