import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSettings } from '../SettingsContext';
import { useModal } from '../ModalContext';
import { useConfirmDialog } from '../ConfirmDialogContext';
import { useNotifications } from '../NotificationsContext';
import { ApiError } from '../shared/api/ApiError';
import {
  deleteWordPackRequest,
  fetchWordPackList,
  regenerateWordPackRequest,
  updateGuestPublicFlag,
} from '../features/wordpack/api';
import { useAbortableAsync, AbortError } from '../lib/hooks';
import { loadSessionState, saveSessionState } from '../lib/storage';
import { assignSetValues, retainSetValues, toggleSetValue } from '../lib/set';
import { Modal } from './Modal';
import { ListControls } from './ListControls';
import { WordPackPanel, WordPackPreviewMeta } from './WordPackPanel';
import { LoadingIndicator } from './LoadingIndicator';
import { TTSButton } from './TTSButton';
import { formatDateJst } from '../lib/date';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';
import { APP_EVENTS, dispatchAppEvent } from '../shared/events/appEvents';
import type { WordPackListItem } from '../features/wordpack/types';
import { Button } from '../shared/ui';

type MiniIconName = 'book' | 'calendar' | 'check' | 'globe' | 'lock' | 'open' | 'speaker' | 'trash' | 'tag' | 'more';

const MiniIcon: React.FC<{ name: MiniIconName }> = ({ name }) => {
  const common = {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.9,
    strokeLinecap: 'round' as const,
    strokeLinejoin: 'round' as const,
    'aria-hidden': true,
    focusable: false,
  };

  switch (name) {
    case 'book':
      return <svg {...common}><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H20v16H7.5A2.5 2.5 0 0 0 5 21V5.5Z" /><path d="M5 5.5A2.5 2.5 0 0 0 2.5 3H2v16h.5A2.5 2.5 0 0 1 5 21" /></svg>;
    case 'calendar':
      return <svg {...common}><path d="M7 3v3M17 3v3M4 8h16M5 5h14a1 1 0 0 1 1 1v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a1 1 0 0 1 1-1Z" /></svg>;
    case 'check':
      return <svg {...common}><path d="M20 6 9 17l-5-5" /></svg>;
    case 'globe':
      return <svg {...common}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.2 2.4 3.3 5.4 3.3 9S14.2 18.6 12 21M12 3C9.8 5.4 8.7 8.4 8.7 12S9.8 18.6 12 21" /></svg>;
    case 'lock':
      return <svg {...common}><path d="M7 10V8a5 5 0 0 1 10 0v2" /><rect x="5" y="10" width="14" height="11" rx="2" /></svg>;
    case 'open':
      return <svg {...common}><path d="M5 12h11M12 6l6 6-6 6" /></svg>;
    case 'speaker':
      return <svg {...common}><path d="M4 10v4h4l5 4V6l-5 4H4Z" /><path d="M16 9.5a4 4 0 0 1 0 5" /></svg>;
    case 'trash':
      return <svg {...common}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 14h10l1-14M9 7V4h6v3" /></svg>;
    case 'tag':
      return <svg {...common}><path d="M20 13 13 20 4 11V4h7l9 9Z" /><path d="M7.5 7.5h.01" /></svg>;
    case 'more':
      return <svg {...common}><path d="M6 12h.01M12 12h.01M18 12h.01" /></svg>;
    default:
      return null;
  }
};

type SortKey = 'created_at' | 'updated_at' | 'lemma' | 'total_examples';
type SortOrder = 'asc' | 'desc';
type ViewMode = 'card' | 'list';
type GenerationFilter = 'all' | 'generated' | 'not_generated';
type VisibilityFilter = 'all' | 'public' | 'private';
type SearchMode = 'prefix' | 'suffix' | 'contains';

interface WordPackListItemWithTotal extends WordPackListItem {
  totalExamples: number;
}

type PersistedState = {
  sortKey: SortKey;
  sortOrder: SortOrder;
  viewMode: ViewMode;
  generationFilter: GenerationFilter;
  visibilityFilter: VisibilityFilter;
  searchMode: SearchMode;
  searchInput: string;
  appliedSearch: { mode: SearchMode; value: string } | null;
  offset: number;
  showAllSense: boolean;
};

const STORAGE_KEY = 'wp.list.ui_state.v1';
const PAGE_LIMIT = 200;
const SEARCH_MODE_LABELS: Record<SearchMode, string> = {
  prefix: '前方一致',
  suffix: '後方一致',
  contains: '部分一致',
};
const GENERATION_FILTER_LABELS: Record<Exclude<GenerationFilter, 'all'>, string> = {
  generated: '生成済み',
  not_generated: '未生成',
};
const VISIBILITY_FILTER_LABELS: Record<Exclude<VisibilityFilter, 'all'>, string> = {
  public: '公開中',
  private: '非公開',
};

const DEFAULT_PERSISTED_STATE: PersistedState = {
  sortKey: 'updated_at',
  sortOrder: 'desc',
  viewMode: 'card',
  generationFilter: 'all',
  visibilityFilter: 'all',
  searchMode: 'contains',
  searchInput: '',
  appliedSearch: null,
  offset: 0,
  showAllSense: false,
};

const sumExamples = (counts?: WordPackListItem['examples_count']): number => {
  if (!counts) return 0;
  return Object.values(counts).reduce((sum, count) => sum + count, 0);
};

const matchString = (text: string, query: string, mode: SearchMode): boolean => {
  if (!query) return true;
  if (mode === 'prefix') return text.startsWith(query);
  if (mode === 'suffix') return text.endsWith(query);
  return text.includes(query);
};

interface WordPackListStateProps {
  id: string;
  title: string;
  description: string;
  symbol: string;
  tone: 'empty' | 'no-results' | 'error';
  detail?: string;
  conditions?: string[];
  actions?: React.ReactNode;
}

const WordPackListState: React.FC<WordPackListStateProps> = ({
  id,
  title,
  description,
  symbol,
  tone,
  detail,
  conditions = [],
  actions,
}) => (
  <section className={`wp-list-state is-${tone}`} aria-labelledby={`${id}-title`}>
    <div
      className="wp-list-state__message"
      role={tone === 'error' ? 'alert' : 'status'}
      aria-live={tone === 'error' ? 'assertive' : 'polite'}
    >
      <span className="wp-list-state__symbol" aria-hidden="true">{symbol}</span>
      <div>
        <h3 id={`${id}-title`}>{title}</h3>
        <p>{description}</p>
        {detail ? <p className="wp-list-state__detail">{detail}</p> : null}
      </div>
    </div>
    {conditions.length > 0 ? (
      <div className="wp-list-state__conditions">
        <span>現在の条件</span>
        <ul aria-label="現在適用中の条件">
          {conditions.map((condition) => <li key={condition}>{condition}</li>)}
        </ul>
      </div>
    ) : null}
    {actions ? <div className="wp-list-state__actions">{actions}</div> : null}
  </section>
);

export const WordPackListPanel: React.FC = () => {
  const { isGuest } = useAuth();
  const { settings } = useSettings();
  const {
    apiBase,
    pronunciationEnabled,
    regenerateScope,
    requestTimeoutMs,
    reasoningEffort,
    textVerbosity,
    model,
  } = settings;
  const { setModalOpen } = useModal();
  const confirmDialog = useConfirmDialog();
  const { add: addNotification, update: updateNotification } = useNotifications();
  const [wordPacks, setWordPacks] = useState<WordPackListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [msg, setMsg] = useState<{ kind: 'status' | 'alert'; text: string } | null>(null);
  const [total, setTotal] = useState(0);
  const persistedState = useMemo(() => loadSessionState<PersistedState>(STORAGE_KEY, DEFAULT_PERSISTED_STATE), []);
  const [offset, setOffset] = useState(() => persistedState.offset);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewWordPackId, setPreviewWordPackId] = useState<string | null>(null);
  const modalFocusRef = useRef<HTMLElement>(null);
  const [sortKey, setSortKey] = useState<SortKey>(persistedState.sortKey);
  const [sortOrder, setSortOrder] = useState<SortOrder>(persistedState.sortOrder);
  const [viewMode, setViewMode] = useState<ViewMode>(persistedState.viewMode);
  const [generationFilter, setGenerationFilter] = useState<GenerationFilter>(persistedState.generationFilter);
  const [visibilityFilter, setVisibilityFilter] = useState<VisibilityFilter>(persistedState.visibilityFilter ?? 'all');
  const [searchMode, setSearchMode] = useState<SearchMode>(persistedState.searchMode);
  const [searchInput, setSearchInput] = useState(persistedState.searchInput);
  const [appliedSearch, setAppliedSearch] = useState<{ mode: SearchMode; value: string } | null>(persistedState.appliedSearch);
  const [senseOpenIds, setSenseOpenIds] = useState<Set<string>>(() => new Set());
  const [showAllSense, setShowAllSense] = useState(persistedState.showAllSense);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [actionMenuOpenId, setActionMenuOpenId] = useState<string | null>(null);
  const [generatingIds, setGeneratingIds] = useState<Set<string>>(() => new Set());
  const [guestPublicUpdatingIds, setGuestPublicUpdatingIds] = useState<Set<string>>(() => new Set());
  const { run: runAbortable } = useAbortableAsync();
  const listRequestIdRef = useRef(0);
  const previewMeta = useMemo<WordPackPreviewMeta | null>(() => {
    if (!previewWordPackId) return null;
    const meta = wordPacks.find((w) => w.id === previewWordPackId);
    if (!meta) return null;
    return {
      id: meta.id,
      lemma: meta.lemma,
      senseTitle: meta.sense_title,
      created_at: meta.created_at,
      updated_at: meta.updated_at,
    };
  }, [previewWordPackId, wordPacks]);
  const clearSelection = useCallback(() => {
    setSelectedIds(new Set());
  }, []);
  useEffect(() => {
    const stateToPersist: PersistedState = {
      sortKey,
      sortOrder,
      viewMode,
      generationFilter,
      visibilityFilter,
      searchMode,
      searchInput,
      appliedSearch,
      offset,
      showAllSense,
    };
    saveSessionState(STORAGE_KEY, stateToPersist);
  }, [sortKey, sortOrder, viewMode, generationFilter, visibilityFilter, searchMode, searchInput, appliedSearch, offset, showAllSense]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ mode?: SearchMode; value?: string }>).detail;
      const nextMode = detail?.mode ?? 'contains';
      const nextValue = (detail?.value ?? '').trim();
      setSearchMode(nextMode);
      setSearchInput(nextValue);
      setAppliedSearch(nextValue ? { mode: nextMode, value: nextValue } : null);
    };
    try { window.addEventListener('wordpack:list-search', handler as EventListener); } catch {}
    return () => {
      try { window.removeEventListener('wordpack:list-search', handler as EventListener); } catch {}
    };
  }, []);

  // 一覧の取得は他のフィルタ操作と競合するため、AbortController を共通化して最新の結果のみを反映させる。
  const loadWordPacks = useCallback(
    async (newOffset: number = 0) => {
      const requestId = listRequestIdRef.current + 1;
      listRequestIdRef.current = requestId;
      setLoading(true);
      setListLoading(true);
      setListError(null);
      setMsg(null);

      try {
        const res = await runAbortable((signal) =>
          fetchWordPackList(apiBase, {
            limit: PAGE_LIMIT,
            offset: newOffset,
            signal,
          }),
        );
        if (requestId !== listRequestIdRef.current) return;
        setWordPacks(
          res.items.map((item) => ({
            ...item,
            checked_only_count: item.checked_only_count ?? 0,
            learned_count: item.learned_count ?? 0,
            guest_public: item.guest_public ?? false,
          })),
        );
        setTotal(res.total);
        setOffset((prev) => (prev === newOffset ? prev : newOffset));
      } catch (e) {
        if (e instanceof AbortError) return;
        if (requestId !== listRequestIdRef.current) return;
        const m = e instanceof ApiError ? e.message : 'WordPack一覧の読み込みに失敗しました';
        setListError(m);
      } finally {
        if (requestId === listRequestIdRef.current) {
          setListLoading(false);
          setLoading(false);
        }
      }
    },
    [apiBase, runAbortable],
  );

  const applyStudyProgress = useCallback(
    (payload: { wordPackId: string; checked_only_count: number; learned_count: number }) => {
      if (!payload?.wordPackId) return;
      setWordPacks((prev) =>
        prev.map((wp) =>
          wp.id === payload.wordPackId
            ? { ...wp, checked_only_count: payload.checked_only_count, learned_count: payload.learned_count }
            : wp,
        ),
      );
    },
    [],
  );

  const generateWordPack = useCallback(async (wordPack: WordPackListItem) => {
    const id = wordPack.id;
    const lemmaLabel = (wordPack.lemma ?? '').trim() || 'WordPack';
    setGeneratingIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
    setMsg(null);
    try {
      await regenerateWordPackRequest({
        apiBase,
        wordPackId: id,
        settings: {
          pronunciationEnabled,
          regenerateScope,
          requestTimeoutMs,
          reasoningEffort,
          textVerbosity,
        },
        model,
        lemma: lemmaLabel,
        notify: { add: addNotification, update: updateNotification },
        messages: {
          progress: 'WordPackを生成しています',
          success: '生成が完了しました',
          failure: 'WordPackの生成に失敗しました',
        },
      });
      setMsg({ kind: 'status', text: `【${lemmaLabel}】の例文生成が完了しました` });
    } catch (e) {
      const m = e instanceof ApiError ? e.message : 'WordPackの生成に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setGeneratingIds((prev) => {
        if (!prev.has(id)) return prev;
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, [
    addNotification,
    apiBase,
    model,
    pronunciationEnabled,
    regenerateScope,
    requestTimeoutMs,
    textVerbosity,
    reasoningEffort,
    updateNotification,
  ]);

  const updateGuestPublic = useCallback(
    async (wordPackId: string, nextValue: boolean) => {
      if (!wordPackId) return;
      if (guestPublicUpdatingIds.has(wordPackId)) return;
      const previous = wordPacks.find((wp) => wp.id === wordPackId)?.guest_public ?? false;
      setGuestPublicUpdatingIds((prev) => new Set(prev).add(wordPackId));
      setWordPacks((prev) =>
        prev.map((wp) => (wp.id === wordPackId ? { ...wp, guest_public: nextValue } : wp)),
      );
      try {
        await updateGuestPublicFlag({
          apiBase,
          wordPackId,
          guestPublic: nextValue,
          timeoutMs: requestTimeoutMs,
        });
        setMsg({ kind: 'status', text: nextValue ? 'ゲスト公開を有効にしました' : 'ゲスト公開を解除しました' });
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      } catch (e) {
        setWordPacks((prev) =>
          prev.map((wp) => (wp.id === wordPackId ? { ...wp, guest_public: previous } : wp)),
        );
        const m = e instanceof ApiError ? e.message : 'ゲスト公開の更新に失敗しました';
        setMsg({ kind: 'alert', text: m });
      } finally {
        setGuestPublicUpdatingIds((prev) => {
          if (!prev.has(wordPackId)) return prev;
          const next = new Set(prev);
          next.delete(wordPackId);
          return next;
        });
      }
    },
    [apiBase, guestPublicUpdatingIds, requestTimeoutMs, wordPacks],
  );

  const deleteWordPack = useCallback(async (wordPack: WordPackListItem) => {
    const targetLabel = wordPack.lemma?.trim() || 'WordPack';
    const confirmed = await confirmDialog(targetLabel);
    if (!confirmed) return;

    setLoading(true);
    setMsg(null);

    try {
      await deleteWordPackRequest(apiBase, wordPack.id);
      setMsg({ kind: 'status', text: 'WordPackを削除しました' });
      await loadWordPacks(offset);
      setSelectedIds((prev) => (prev.has(wordPack.id) ? toggleSetValue(prev, wordPack.id) : prev));
    } catch (e) {
      const m = e instanceof ApiError ? e.message : 'WordPackの削除に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  }, [apiBase, confirmDialog, loadWordPacks, offset]);

  useEffect(() => {
    loadWordPacks();
  }, [loadWordPacks]);

  useEffect(() => {
    const onUpdated = () => { loadWordPacks(offset); };
    try { window.addEventListener('wordpack:updated', onUpdated as EventListener); } catch {}
    return () => {
      try { window.removeEventListener('wordpack:updated', onUpdated as EventListener); } catch {}
    };
  }, [loadWordPacks, offset]);

  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ wordPackId?: string; checked_only_count?: number; learned_count?: number }>).detail;
      if (!detail || typeof detail !== 'object' || !detail.wordPackId) return;
      applyStudyProgress({
        wordPackId: detail.wordPackId,
        checked_only_count: typeof detail.checked_only_count === 'number' ? detail.checked_only_count : 0,
        learned_count: typeof detail.learned_count === 'number' ? detail.learned_count : 0,
      });
    };
    try { window.addEventListener('wordpack:study-progress', handler as EventListener); } catch {}
    return () => {
      try { window.removeEventListener('wordpack:study-progress', handler as EventListener); } catch {}
    };
  }, [applyStudyProgress]);

  useEffect(() => {
    setSenseOpenIds((prev) => {
      if (prev.size === 0) return prev;
      const next = retainSetValues(prev, wordPacks.map((wp) => wp.id));
      return next.size === prev.size ? prev : next;
    });
  }, [wordPacks]);

  useEffect(() => {
    setSelectedIds((prev) => {
      if (prev.size === 0) return prev;
      const next = retainSetValues(prev, wordPacks.map((wp) => wp.id));
      return next.size === prev.size ? prev : next;
    });
  }, [wordPacks]);

  const formatDate = (dateStr: string) => formatDateJst(dateStr);

  const normalizedSearch = useMemo(() => {
    if (!appliedSearch) return null;
    const value = appliedSearch.value.trim().toLowerCase();
    if (!value) return null;
    return { mode: appliedSearch.mode, value };
  }, [appliedSearch]);

  const normalizedWordPacks = useMemo<WordPackListItemWithTotal[]>(
    () =>
      wordPacks.map((wp) => ({
        ...wp,
        totalExamples: sumExamples(wp.examples_count),
      })),
    [wordPacks]
  );

  const filteredWordPacks = useMemo(() => {
    return normalizedWordPacks.filter((wp) => {
      if (visibilityFilter === 'public' && !wp.guest_public) return false;
      if (visibilityFilter === 'private' && wp.guest_public) return false;
      if (generationFilter === 'generated' && wp.totalExamples <= 0) return false;
      if (generationFilter === 'not_generated' && wp.totalExamples > 0) return false;
      if (normalizedSearch) {
        const lemma = (wp.lemma || '').toLowerCase();
        if (!matchString(lemma, normalizedSearch.value, normalizedSearch.mode)) return false;
      }
      return true;
    });
  }, [normalizedWordPacks, visibilityFilter, generationFilter, normalizedSearch]);

  const sortedWordPacks = useMemo(() => {
    return [...filteredWordPacks].sort((a, b) => {
      let aValue: string | number;
      let bValue: string | number;

      switch (sortKey) {
        case 'created_at':
        case 'updated_at':
          aValue = new Date(a[sortKey]).getTime();
          bValue = new Date(b[sortKey]).getTime();
          break;
        case 'lemma':
          aValue = a.lemma.toLowerCase();
          bValue = b.lemma.toLowerCase();
          break;
        case 'total_examples':
          aValue = a.totalExamples;
          bValue = b.totalExamples;
          break;
        default:
          return 0;
      }

      if (aValue < bValue) return sortOrder === 'asc' ? -1 : 1;
      if (aValue > bValue) return sortOrder === 'asc' ? 1 : -1;
      return 0;
    });
  }, [filteredWordPacks, sortKey, sortOrder]);

  const previewNavigationIds = useMemo(() => sortedWordPacks.map((wp) => wp.id), [sortedWordPacks]);
  const visibleWordPackIds = useMemo(() => sortedWordPacks.map((wp) => wp.id), [sortedWordPacks]);
  const selectedCount = selectedIds.size;
  const visibleSelectedCount = useMemo(
    () => sortedWordPacks.reduce((sum, wp) => (selectedIds.has(wp.id) ? sum + 1 : sum), 0),
    [sortedWordPacks, selectedIds]
  );
  const allVisibleSelected = sortedWordPacks.length > 0 && visibleSelectedCount === sortedWordPacks.length;

  const toggleVisibleSelection = useCallback(() => {
    setSelectedIds((prev) => assignSetValues(prev, visibleWordPackIds, !allVisibleSelected));
  }, [allVisibleSelected, visibleWordPackIds]);

  const deleteSelectedWordPacks = useCallback(async () => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    const confirmed = await confirmDialog(`選択中のWordPack（${ids.length}件）`);
    if (!confirmed) return;

    setLoading(true);
    setMsg(null);
    let deleted = 0;
    let failure: string | null = null;
    try {
      for (const id of ids) {
        try {
          await deleteWordPackRequest(apiBase, id);
          deleted += 1;
        } catch (error) {
          const err = error instanceof ApiError ? error.message : 'WordPackの削除に失敗しました';
          failure = err;
          break;
        }
      }
      if (deleted > 0) {
        await loadWordPacks(offset);
        clearSelection();
      }
      if (failure) {
        const text = deleted > 0
          ? `WordPackを${deleted}件削除しましたが一部失敗しました: ${failure}`
          : `WordPackの削除に失敗しました: ${failure}`;
        setMsg({ kind: 'alert', text });
      } else if (deleted > 0) {
        setMsg({ kind: 'status', text: `WordPackを${deleted}件削除しました` });
      } else {
        setMsg({ kind: 'alert', text: '削除対象がありません' });
      }
    } finally {
      setLoading(false);
    }
  }, [selectedIds, confirmDialog, apiBase, loadWordPacks, offset, clearSelection]);

  const updateSelectedGuestPublic = useCallback(
    async (nextValue: boolean) => {
      const ids = Array.from(selectedIds);
      if (ids.length === 0) return;
      setLoading(true);
      setMsg(null);
      const previous = wordPacks;
      setWordPacks((prev) =>
        prev.map((wp) => (selectedIds.has(wp.id) ? { ...wp, guest_public: nextValue } : wp)),
      );
      let updated = 0;
      let failure: string | null = null;
      try {
        for (const id of ids) {
          try {
            await updateGuestPublicFlag({
              apiBase,
              wordPackId: id,
              guestPublic: nextValue,
              timeoutMs: requestTimeoutMs,
            });
            updated += 1;
          } catch (error) {
            failure = error instanceof ApiError ? error.message : '公開設定の更新に失敗しました';
            break;
          }
        }
        if (failure) {
          setWordPacks(previous);
          setMsg({ kind: 'alert', text: `公開設定を${updated}件更新しましたが一部失敗しました: ${failure}` });
          return;
        }
        setMsg({ kind: 'status', text: nextValue ? `WordPackを${updated}件公開にしました` : `WordPackを${updated}件非公開にしました` });
        dispatchAppEvent(APP_EVENTS.wordPackUpdated);
      } finally {
        setLoading(false);
      }
    },
    [apiBase, requestTimeoutMs, selectedIds, wordPacks],
  );

  const handleApplySearch = useCallback(() => {
    setAppliedSearch({ mode: searchMode, value: searchInput.trim() });
  }, [searchMode, searchInput]);

  const clearAppliedSearch = useCallback(() => {
    setSearchInput('');
    setAppliedSearch(null);
    try { window.dispatchEvent(new Event('wordpack:list-search-cleared')); } catch {}
  }, []);

  const clearFilters = useCallback(() => {
    setVisibilityFilter('all');
    setGenerationFilter('all');
  }, []);

  const requestCreateWordPackFocus = useCallback(() => {
    try { window.dispatchEvent(new Event('wordpack:create-focus')); } catch {}
  }, []);

  const handleSortChange = useCallback(
    (newSortKey: SortKey) => {
      if (sortKey === newSortKey) {
        setSortOrder((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      } else {
        setSortKey(newSortKey);
        setSortOrder('desc');
      }
    },
    [sortKey]
  );

  const toggleSenseOpen = useCallback((id: string) => {
    setSenseOpenIds((prev) => toggleSetValue(prev, id));
  }, []);

  const toggleAllSense = useCallback(() => {
    setShowAllSense((prev) => {
      const next = !prev;
      setSenseOpenIds(next ? new Set(wordPacks.map((wp) => wp.id)) : new Set());
      return next;
    });
  }, [wordPacks]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => toggleSetValue(prev, id));
  }, []);

  const toggleActionMenu = useCallback((id: string) => {
    setActionMenuOpenId((prev) => (prev === id ? null : id));
  }, []);

  useEffect(() => {
    if (!actionMenuOpenId) return;
    const openId = actionMenuOpenId;
    const focusFrame = window.requestAnimationFrame(() => {
      const menu = document.getElementById(`wp-action-menu-${openId}`);
      menu?.querySelector<HTMLElement>('button[role]:not(:disabled)')?.focus();
    });
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      setActionMenuOpenId(null);
      window.requestAnimationFrame(() => {
        document.getElementById(`wp-action-trigger-${openId}`)?.focus();
      });
    };
    const closeOnOutsidePointer = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      const menu = document.getElementById(`wp-action-menu-${openId}`);
      const trigger = document.getElementById(`wp-action-trigger-${openId}`);
      if (menu?.contains(target) || trigger?.contains(target)) return;
      setActionMenuOpenId(null);
    };
    document.addEventListener('keydown', closeOnEscape);
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    return () => {
      window.cancelAnimationFrame(focusFrame);
      document.removeEventListener('keydown', closeOnEscape);
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
    };
  }, [actionMenuOpenId]);

  useEffect(() => {
    setActionMenuOpenId(null);
  }, [viewMode]);

  useEffect(() => {
    if (showAllSense) {
      setSenseOpenIds(new Set(wordPacks.map((wp) => wp.id)));
    }
  }, [showAllSense, wordPacks]);

  const resolveSenseTitle = useCallback((title?: string) => {
    const trimmed = (title ?? '').trim();
    return trimmed || '語義タイトル未設定';
  }, []);

  const hasNext = offset + PAGE_LIMIT < total;
  const hasPrev = offset > 0;
  const generatedCount = normalizedWordPacks.filter((wp) => wp.totalExamples > 0).length;
  const emptyCount = normalizedWordPacks.length - generatedCount;
  const publicCount = normalizedWordPacks.filter((wp) => wp.guest_public).length;
  const privateCount = normalizedWordPacks.length - publicCount;
  const recentWordPacks = useMemo(
    () =>
      [...normalizedWordPacks]
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 3),
    [normalizedWordPacks],
  );
  const hasAppliedSearch = normalizedSearch !== null;
  const hasActiveFilters = generationFilter !== 'all' || visibilityFilter !== 'all';
  const activeConditionLabels = useMemo(() => {
    const conditions: string[] = [];
    if (appliedSearch?.value.trim()) {
      conditions.push(`検索: ${appliedSearch.value.trim()}（${SEARCH_MODE_LABELS[appliedSearch.mode]}）`);
    }
    if (visibilityFilter !== 'all') {
      conditions.push(`公開状態: ${VISIBILITY_FILTER_LABELS[visibilityFilter]}`);
    }
    if (generationFilter !== 'all') {
      conditions.push(`生成状態: ${GENERATION_FILTER_LABELS[generationFilter]}`);
    }
    return conditions;
  }, [appliedSearch, generationFilter, visibilityFilter]);
  const isInitialListLoading = listLoading && wordPacks.length === 0;
  const hasUnavailableInitialList = Boolean(listError) && wordPacks.length === 0;
  const showInitialEmpty = !listLoading && !listError && wordPacks.length === 0;
  const showNoResults = wordPacks.length > 0 && sortedWordPacks.length === 0;
  const showListControls = wordPacks.length > 0;
  const noResultsTitle =
    hasAppliedSearch && hasActiveFilters
      ? '検索・絞り込み条件に一致するWordPackがありません'
      : hasAppliedSearch
        ? '検索条件に一致するWordPackがありません'
        : '絞り込み条件に一致するWordPackがありません';
  const noResultsResetLabel =
    hasAppliedSearch && hasActiveFilters
      ? 'すべての条件を解除'
      : hasAppliedSearch
        ? '検索を解除'
        : '絞り込みを解除';
  const resetNoResultsConditions = useCallback(() => {
    if (hasAppliedSearch) clearAppliedSearch();
    if (hasActiveFilters) clearFilters();
  }, [clearAppliedSearch, clearFilters, hasActiveFilters, hasAppliedSearch]);
  const openPreview = useCallback((wordPackId: string) => {
    setActionMenuOpenId(null);
    setPreviewWordPackId(wordPackId);
    setPreviewOpen(true);
    setModalOpen(true);
  }, [setModalOpen]);
  const closePreview = useCallback(() => {
    setPreviewOpen(false);
    setPreviewWordPackId(null);
    setModalOpen(false);
  }, [setModalOpen]);
  const previewNavigationState = useMemo(() => {
    if (!previewWordPackId) return null;
    const index = previewNavigationIds.indexOf(previewWordPackId);
    if (index < 0) return null;
    return {
      index,
      total: previewNavigationIds.length,
      previousId: index > 0 ? previewNavigationIds[index - 1] : null,
      nextId: index < previewNavigationIds.length - 1 ? previewNavigationIds[index + 1] : null,
    };
  }, [previewNavigationIds, previewWordPackId]);

  const handleActionMenuKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    const items = Array.from(
      event.currentTarget.querySelectorAll<HTMLButtonElement>('button[role]:not(:disabled)'),
    );
    if (items.length === 0) return;

    event.preventDefault();
    const currentIndex = items.indexOf(document.activeElement as HTMLButtonElement);
    const nextIndex =
      event.key === 'Home'
        ? 0
        : event.key === 'End'
          ? items.length - 1
          : event.key === 'ArrowUp'
            ? (currentIndex <= 0 ? items.length - 1 : currentIndex - 1)
            : (currentIndex + 1) % items.length;
    items[nextIndex]?.focus();
  };

  const renderWordPackActionMenu = (wordPack: WordPackListItemWithTotal, placement: 'card' | 'list') => (
    <div
      id={`wp-action-menu-${wordPack.id}`}
      className={`wp-card-menu${placement === 'list' ? ' wp-index-action-menu' : ''}`}
      role="menu"
      aria-label={`${wordPack.lemma} の操作メニュー`}
      onClick={(event) => event.stopPropagation()}
      onKeyDown={handleActionMenuKeyDown}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setActionMenuOpenId(null);
        }
      }}
    >
      {placement === 'card' ? (
        <button type="button" role="menuitem" onClick={() => openPreview(wordPack.id)}>
          開く
        </button>
      ) : null}
      {wordPack.is_empty ? (
        <GuestLock isGuest={isGuest}>
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setActionMenuOpenId(null);
              generateWordPack(wordPack);
            }}
            disabled={loading || generatingIds.has(wordPack.id)}
          >
            {generatingIds.has(wordPack.id) ? '例文を生成中' : '例文を生成'}
          </button>
        </GuestLock>
      ) : null}
      {placement === 'list' ? (
        <>
          <TTSButton
            text={wordPack.lemma}
            ariaLabel={`${wordPack.lemma}の音声を再生`}
            label="音声を再生"
            className="wp-action-menu-tts"
            role="menuitem"
            icon={<MiniIcon name="speaker" />}
          />
          <button
            type="button"
            role="menuitemcheckbox"
            aria-checked={showAllSense || senseOpenIds.has(wordPack.id)}
            disabled={showAllSense}
            title={showAllSense ? '語義一括表示が有効なため、個別の表示切替はできません' : undefined}
            onClick={() => {
              setActionMenuOpenId(null);
              toggleSenseOpen(wordPack.id);
            }}
          >
            {showAllSense
              ? '語義は一括表示中'
              : senseOpenIds.has(wordPack.id)
                ? '語義を隠す'
                : '語義を表示'}
          </button>
        </>
      ) : null}
      <GuestLock isGuest={isGuest}>
        <button
          type="button"
          role="menuitem"
          onClick={() => {
            setActionMenuOpenId(null);
            updateGuestPublic(wordPack.id, !wordPack.guest_public);
          }}
          disabled={loading || guestPublicUpdatingIds.has(wordPack.id)}
        >
          {guestPublicUpdatingIds.has(wordPack.id)
            ? 'ゲスト公開設定を更新中'
            : wordPack.guest_public
              ? 'ゲスト公開を解除'
              : 'ゲスト公開にする'}
        </button>
      </GuestLock>
      <GuestLock isGuest={isGuest}>
        <button
          type="button"
          role="menuitem"
          className="wp-card-menu-danger"
          onClick={(event) => {
            setActionMenuOpenId(null);
            deleteWordPack(wordPack);
            event.stopPropagation();
          }}
          disabled={loading}
        >
          削除
        </button>
      </GuestLock>
    </div>
  );

  return (
    <section>
      <style>{`
        .wp-list-container { max-width: 100%; }
        .wp-list-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; max-height: 40px; }
        .wp-sort-controls { display: flex; align-items: center; gap: 0.3rem; margin-bottom: 0.5rem; }
        .wp-sort-select,
        .wp-filter-select,
        .wp-search-input {
          padding: 0.25rem;
          border: 1px solid #cbd5e1;
          border-radius: 4px;
          background: #ffffff;
          color: #0f172a;
        }
        .wp-sort-button,
        .wp-search-button,
        .wp-pagination button,
        .wp-list-header > button {
          padding: 0.25rem 0.75rem;
          border: 1px solid #cbd5e1;
          border-radius: 4px;
          background: #ffffff;
          color: #0f172a;
          cursor: pointer;
        }
        .wp-sort-button { display: flex; align-items: center; gap: 0.25rem; }
        .wp-sort-button:hover:not(:disabled),
        .wp-search-button:hover:not(:disabled),
        .wp-pagination button:hover:not(:disabled),
        .wp-list-header > button:hover:not(:disabled) {
          background: #f8fafc;
        }
        .wp-sort-button.active {
          background: #e3f2fd;
          border-color: #2196f3;
          color: #0f4d73;
        }
        .wp-sort-button:disabled,
        .wp-search-button:disabled,
        .wp-pagination button:disabled,
        .wp-list-header > button:disabled {
          background: #e5e7eb;
          color: #374151;
          cursor: not-allowed;
        }
        .wp-list-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 1rem; }
        .wp-card { border: 1px solid #ddd; border-radius: 5px; padding: 0.2rem; background:rgb(173, 159, 211); box-shadow: 0 2px 4px rgba(0,0,0,0.1); cursor: pointer; }
        .wp-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem; gap: 0.5rem; }
        .wp-card-actions { display: grid; grid-template-rows: auto auto; gap: 0.15rem; margin-left: auto; }
        .wp-card-actions-upper { display: flex; gap: 0.15rem; align-items: center; }
        .wp-card-actions-lower { display: flex; gap: 0.15rem; align-items: center; justify-content: flex-end; }
        .wp-card-tts-btn { font-size: 0.82rem; padding: 0.15rem 0.45rem; border: 1px solid #cbd5e1; border-radius: 4px; background: #ffffff; color: #0f172a; cursor: pointer; }
        .wp-card-title { font-size: 1rem; font-weight: bold; color: #333; margin: 0; }
        .wp-card-meta { font-size: 0.88rem; color: #333; margin: 0.25rem 0; }
        .wp-progress-badges { display: flex; gap: 0.35rem; flex-wrap: wrap; margin-top: 0.35rem; }
        .wp-progress-badge { display: inline-flex; align-items: center; gap: 0.2rem; padding: 0.15rem 0.45rem; border-radius: 999px; font-size: 0.8rem; font-weight: bold; border: 1px solid transparent; }
        .wp-progress-badge.learned { background: #e8f5e9; border-color: #81c784; color: #1b5e20; }
        .wp-progress-badge.checked { background: #fff3e0; border-color: #ffcc80; color: #ef6c00; }
        .wp-progress-badge.small { font-size: 0.75rem; padding: 0.1rem 0.35rem; }
        .wp-card-header-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
        .wp-sense-btn { font-size: 0.82rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid #5c6bc0; background: #f5f7ff; color: #3f51b5; cursor: pointer; }
        .wp-sense-btn[aria-pressed="true"] { background: #e8eaf6; border-color: #3f51b5; color: #283593; }
        .wp-generate-btn { font-size: 0.82rem; padding: 0.15rem 0.45rem; border-radius: 4px; border: 1px solid #2e7d32; background: #e8f5e9; color: #1b5e20; cursor: pointer; }
        .wp-generate-btn:hover:not(:disabled) { background: #d0f0d5; }
        .wp-sense-btn:disabled,
        .wp-generate-btn:disabled,
        .wp-card-tts-btn:disabled,
        .wp-index-tts-btn:disabled {
          border-color: #cbd5e1;
          background: #e5e7eb;
          color: #374151;
          cursor: not-allowed;
        }
        .wp-card-sense-title { margin: 0.35rem 0 0.2rem; font-size: 0.70em; color: #2f2f2f; background: rgba(255,255,255,0.86); padding: 0.25rem 0.35rem; border-left: 3px solid #5c6bc0; border-radius: 4px; line-height: 1.4; }
        .wp-badge { display: inline-block; padding: 0.1rem 0.4rem; border-radius: 999px; font-size: 0.75em; margin-left: 0.5rem; }
        .wp-badge.empty { background: #fff3cd; color: #7a5b00; border: 1px solid #ffe08a; }
        .wp-pagination { display: flex; justify-content: center; gap: 0.5rem; margin-top: 1rem; }
        .wp-view-toggle { display: flex; gap: 0.3rem; align-items: center; margin-bottom: 0.5rem; }
        .wp-toggle-btn { padding: 0.25rem 0.75rem; border: 1px solid #ccc; border-radius: 4px; background: white; color: #0f172a; cursor: pointer; }
        .wp-toggle-btn[aria-pressed="true"] { background: #e3f2fd; border-color: #2196f3; color: #0f4d73; }
        .wp-preview-nav { display: flex; justify-content: space-between; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem; flex-wrap: wrap; }
        .wp-preview-nav__context { margin: 0; color: var(--color-subtle); }
        .wp-preview-nav__actions { display: inline-flex; align-items: center; gap: 0.5rem; margin-left: auto; }
        .wp-preview-nav__actions button { min-height: 2rem; padding: 0.25rem 0.7rem; }
        .wp-preview-nav__position { color: var(--color-subtle); font-size: 0.9rem; }
        .wp-selection-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin-bottom: 0.75rem; font-size: 0.85em; }
        .wp-selection-bar button { padding: 0.25rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; background: #ffffff; color: #0f172a; cursor: pointer; }
        .wp-selection-bar button:disabled { background: #e5e7eb; color: #374151; cursor: not-allowed; }
        .wp-select-checkbox { display: inline-flex; align-items: center; justify-content: center; }
        .wp-select-checkbox input { width: 1rem; height: 1rem; cursor: pointer; }
        @media (max-width: 640px) { 
          .wp-list-grid { grid-template-columns: 1fr; }
          .wp-card-header { flex-direction: column; align-items: flex-start; }
          .wp-card-actions { margin-left: 0; margin-top: 0.3rem; }
          .wp-sort-controls { flex-direction: column; align-items: stretch; }
          .wp-list-header { flex-direction: column; align-items: flex-start; max-height: none; gap: 0.5rem; }
          .wp-list-header button { width: 100%; }
        }
      `}</style>

      <div className="wp-list-container">
        {recentWordPacks.length > 0 && !hasAppliedSearch && !hasActiveFilters ? (
          <section className="wp-recent-panel" aria-labelledby="wp-recent-heading">
            <div className="wp-recent-panel-header">
              <div>
                <h2 id="wp-recent-heading">最近開いたWordPack</h2>
                <p>直近で更新された辞書記事へすぐ戻れます。</p>
              </div>
              <a href="#wp-saved-list-heading">すべて見る</a>
            </div>
            <div className="wp-recent-list">
              {recentWordPacks.map((wp, index) => (
                <button
                  key={wp.id}
                  type="button"
                  className="wp-recent-item"
                  onClick={() => openPreview(wp.id)}
                >
                  <span className={`wp-recent-bookmark wp-recent-bookmark-${index + 1}`} aria-hidden="true" />
                  <span>
                    <strong>{wp.lemma}</strong>
                    <small>{formatDate(wp.updated_at)}に更新</small>
                  </span>
                </button>
              ))}
            </div>
          </section>
        ) : null}

        <div className="wp-list-header">
          <h2 id="wp-saved-list-heading">
            <span>保存済みWordPack</span>
            <span
              className="wp-count-pill"
              aria-label={
                isInitialListLoading
                  ? '件数を確認中'
                  : hasUnavailableInitialList
                    ? '件数を取得できませんでした'
                    : `${total}件`
              }
            >
              {isInitialListLoading ? '確認中' : hasUnavailableInitialList ? '未取得' : `${total}件`}
            </span>
          </h2>
          <p className="wp-list-summary">
            {isInitialListLoading
              ? '保存済みWordPackを確認しています'
              : hasUnavailableInitialList
                ? '件数と一覧を取得できませんでした'
                : (
                  <>
                    {total}件中 {sortedWordPacks.length}件を表示
                    <span>生成済み {generatedCount}件</span>
                    <span>未生成 {emptyCount}件</span>
                  </>
                )}
          </p>
          {showListControls ? (
            <div className="wp-view-toggle" role="group" aria-label="表示モード">
              <button
                type="button"
                className="wp-toggle-btn"
                aria-pressed={viewMode === 'card'}
                onClick={() => setViewMode('card')}
                title="カード表示"
              ><MiniIcon name="book" />カード</button>
              <button
                type="button"
                className="wp-toggle-btn"
                aria-pressed={viewMode === 'list'}
                onClick={() => setViewMode('list')}
                title="リスト表示（索引）"
              ><MiniIcon name="more" />リスト</button>
            </div>
          ) : null}
          <button className="wp-refresh-button" onClick={() => loadWordPacks(offset)} disabled={loading}>
            更新
          </button>
        </div>

        {showListControls ? (
          <div className="wp-filter-chip-row" role="group" aria-label="WordPackの絞り込み">
            <button type="button" aria-pressed={visibilityFilter === 'all' && generationFilter === 'all'} onClick={clearFilters}>
              すべて
            </button>
            <button type="button" aria-pressed={visibilityFilter === 'public'} onClick={() => setVisibilityFilter('public')}>
              公開中 <span>{publicCount}</span>
            </button>
            <button type="button" aria-pressed={visibilityFilter === 'private'} onClick={() => setVisibilityFilter('private')}>
              非公開 <span>{privateCount}</span>
            </button>
            <button type="button" aria-pressed={generationFilter === 'generated'} onClick={() => setGenerationFilter('generated')}>
              生成済み <span>{generatedCount}</span>
            </button>
            <button type="button" aria-pressed={generationFilter === 'not_generated'} onClick={() => setGenerationFilter('not_generated')}>
              未生成 <span>{emptyCount}</span>
            </button>
            <span className="wp-filter-chip-more"><span aria-hidden="true">＋</span> フィルター</span>
          </div>
        ) : null}

        {selectedCount > 0 ? (
          <div className="wp-selection-bar" role="group" aria-label="WordPack選択操作">
            <span className="wp-selection-bar__count">{selectedCount}件選択中</span>
            <button type="button" onClick={toggleVisibleSelection} disabled={sortedWordPacks.length === 0}>
              {allVisibleSelected ? '選択を減らす' : '表示中を全選択'}
            </button>
            <button type="button" onClick={clearSelection}>
              選択を解除
            </button>
            <GuestLock isGuest={isGuest}>
              <button type="button" onClick={() => updateSelectedGuestPublic(true)} disabled={loading}>
                <MiniIcon name="globe" />公開にする
              </button>
            </GuestLock>
            <GuestLock isGuest={isGuest}>
              <button type="button" onClick={() => updateSelectedGuestPublic(false)} disabled={loading}>
                <MiniIcon name="lock" />非公開にする
              </button>
            </GuestLock>
            <span className="wp-selection-tag-placeholder" aria-disabled="true">
              <MiniIcon name="tag" />タグを追加
            </span>
            <GuestLock isGuest={isGuest}>
              <button
                type="button"
                onClick={deleteSelectedWordPacks}
                disabled={loading}
              ><MiniIcon name="trash" />削除</button>
            </GuestLock>
          </div>
        ) : null}

        {showListControls ? (
          <ListControls<SortKey>
            sortKey={sortKey}
            sortOptions={[
              { value: 'updated_at', label: '更新日時' },
              { value: 'created_at', label: '作成日時' },
              { value: 'lemma', label: '単語名' },
              { value: 'total_examples', label: '例文数' },
            ]}
            onChangeSortKey={(key) => handleSortChange(key)}
            sortOrder={sortOrder}
            onChangeSortOrder={setSortOrder}
            searchMode={searchMode}
            onChangeSearchMode={setSearchMode as any}
            searchInput={searchInput}
            onChangeSearchInput={setSearchInput}
            onApplySearch={handleApplySearch}
            showSearch={false}
            filtersLeft={(
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginLeft: '0.5rem' }}>
                <input
                  type="checkbox"
                  role="switch"
                  aria-label="語義一括表示"
                  checked={showAllSense}
                  onChange={toggleAllSense}
                />
                語義一括表示
              </label>
            )}
          />
        ) : null}

        {isInitialListLoading ? (
          <div className="wp-list-loading">
            <LoadingIndicator
              label="WordPack一覧を読み込み中"
              subtext="保存済みデータの件数と一覧を確認しています。"
            />
          </div>
        ) : null}
        {listLoading && wordPacks.length > 0 ? (
          <div className="wp-list-refreshing">
            <LoadingIndicator
              label="WordPack一覧を更新中"
              subtext="前回取得した一覧を表示したまま、最新状態を確認しています。"
            />
          </div>
        ) : null}
        {listError ? (
          <WordPackListState
            id="wp-list-error"
            tone="error"
            symbol="!"
            title={wordPacks.length > 0 ? '最新の一覧に更新できませんでした' : 'WordPack一覧を読み込めませんでした'}
            description={
              wordPacks.length > 0
                ? '前回取得したWordPackを表示しています。画面上の内容は最新でない可能性があります。'
                : '保存済みデータが削除されたわけではありません。通信状態を確認して、もう一度お試しください。'
            }
            detail={`詳細: ${listError}`}
            actions={(
              <Button
                variant="primary"
                className="wp-list-state__action"
                onClick={() => loadWordPacks(wordPacks.length > 0 ? offset : 0)}
                disabled={listLoading}
              >
                {wordPacks.length > 0 ? '更新を再試行' : 'もう一度読み込む'}
              </Button>
            )}
          />
        ) : null}
        {msg && <div role={msg.kind}>{msg.text}</div>}

        {showInitialEmpty ? (
          <WordPackListState
            id="wp-list-empty"
            tone="empty"
            symbol="+"
            title={isGuest ? '公開中のWordPackはまだありません' : '保存済みWordPackはまだありません'}
            description={
              isGuest
                ? '公開されたWordPackが追加されると、ここで閲覧できます。'
                : '見出し語を登録すると、ここから内容を確認・管理できます。'
            }
            actions={
              isGuest ? null : (
                <Button
                  variant="primary"
                  className="wp-list-state__action"
                  onClick={requestCreateWordPackFocus}
                >
                  新しいWordPackを作成
                </Button>
              )
            }
          />
        ) : showNoResults ? (
          <WordPackListState
            id="wp-list-no-results"
            tone="no-results"
            symbol="⌕"
            title={noResultsTitle}
            description="保存済みのWordPackは残っています。条件を解除すると、現在読み込んでいる一覧へ戻れます。"
            conditions={activeConditionLabels}
            actions={(
              <Button
                variant="primary"
                className="wp-list-state__action"
                onClick={resetNoResultsConditions}
              >
                {noResultsResetLabel}
              </Button>
            )}
          />
        ) : wordPacks.length > 0 ? (
          <>
            {viewMode === 'card' ? (
              <div className="wp-list-grid">
                {sortedWordPacks.map((wp) => (
                  <div
                    key={wp.id}
                    className={`wp-card${selectedIds.has(wp.id) ? ' is-selected' : ''}${wp.is_empty ? ' is-empty' : ''}`}
                    data-testid="wp-card"
                    onClick={() => openPreview(wp.id)}
                  >
                    <div className="wp-card-header">
                      <label
                        className="wp-select-checkbox"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <input
                          type="checkbox"
                          checked={selectedIds.has(wp.id)}
                          onChange={() => toggleSelect(wp.id)}
                          aria-label={`WordPack ${wp.lemma} を選択`}
                        />
                      </label>
                      <div className="wp-card-header-main">
                        <h3 className="wp-card-title">{wp.lemma}</h3>
                        <p className="wp-card-description">
                          {wp.sense_title?.trim() || (wp.is_empty ? '例文を追加すると学習パックとして使えます。' : '用例と語義をまとめた学習パックです。')}
                        </p>
                      </div>
                      <button
                        id={`wp-action-trigger-${wp.id}`}
                        type="button"
                        className="wp-card-more"
                        aria-label={`${wp.lemma} のその他の操作`}
                        aria-haspopup="menu"
                        aria-expanded={actionMenuOpenId === wp.id}
                        aria-controls={`wp-action-menu-${wp.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleActionMenu(wp.id);
                        }}
                      >
                        <MiniIcon name="more" />
                        <span>その他</span>
                      </button>
                      {actionMenuOpenId === wp.id ? renderWordPackActionMenu(wp, 'card') : null}
                    </div>
                    {(showAllSense || senseOpenIds.has(wp.id)) && (
                      <div className="wp-card-sense-title" data-testid="wp-card-sense-title">
                        {resolveSenseTitle(wp.sense_title)}
                      </div>
                    )}
                    <div className="wp-card-meta">
                      <div className="wp-progress-badges" aria-label="学習状況">
                        <span className="wp-progress-badge learned">使える {wp.learned_count}</span>
                        <span className="wp-progress-badge checked">確認済み {wp.checked_only_count}</span>
                      </div>
                      <div className="wp-card-status-row">
                        <span className={`wp-visibility-pill ${wp.guest_public ? 'is-public' : 'is-private'}`}>
                          <MiniIcon name={wp.guest_public ? 'globe' : 'lock'} />
                          {wp.guest_public ? '公開中' : '非公開'}
                        </span>
                        <span className="wp-date-pill">
                          <MiniIcon name="calendar" />
                          更新: {formatDate(wp.updated_at)}
                        </span>
                      </div>
                      <div className="wp-card-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="wp-open-button"
                          onClick={() => openPreview(wp.id)}
                        >
                          <MiniIcon name="open" />開く
                        </button>
                        <TTSButton text={wp.lemma} ariaLabel={`${wp.lemma}の音声`} className="wp-card-tts-btn" icon={<MiniIcon name="speaker" />} />
                        {wp.is_empty && (
                          <GuestLock isGuest={isGuest}>
                            <button
                              type="button"
                              className="wp-generate-btn"
                              onClick={(e) => {
                                e.stopPropagation();
                                generateWordPack(wp);
                              }}
                              disabled={loading || generatingIds.has(wp.id)}
                            >生成</button>
                          </GuestLock>
                        )}
                        <button
                          type="button"
                          className="wp-sense-btn"
                          aria-pressed={showAllSense || senseOpenIds.has(wp.id)}
                          disabled={showAllSense}
                          onClick={(e) => {
                            e.stopPropagation();
                            toggleSenseOpen(wp.id);
                          }}
                        ><MiniIcon name="book" />語義</button>
                      </div>
                      {wp.is_empty ? (
                        <div className="wp-example-tags">
                          <span className="wp-example-tag is-empty">
                            例文未生成
                          </span>
                        </div>
                      ) : wp.examples_count && (
                        <div className="wp-example-tags">
                          <div className="wp-example-tag-list">
                            {Object.entries(wp.examples_count).map(([category, count]) => (
                              <span key={category} className={`wp-example-tag${count > 0 ? ' has-count' : ''}`}>
                                <span>{category}</span>
                                <span>{count}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <ul
                className="wp-index-grid"
                aria-label="保存済みWordPackのリスト"
              >
                {sortedWordPacks.map((wp) => (
                  <li
                    key={wp.id}
                    className={`wp-index-item${selectedIds.has(wp.id) ? ' is-selected' : ''}`}
                    data-testid="wp-index-item"
                  >
                    <label className="wp-select-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(wp.id)}
                        onChange={() => toggleSelect(wp.id)}
                        aria-label={`WordPack ${wp.lemma} を選択`}
                      />
                    </label>
                    <div className="wp-index-main">
                      <div className="wp-index-title-row" data-testid="wp-index-title-row">
                        <span className="wp-index-title">{wp.lemma}</span>
                        <span className={`wp-index-meta${wp.is_empty ? ' is-empty' : ''}`}>
                          {wp.is_empty ? '未生成' : `例文 ${wp.totalExamples}件`}
                        </span>
                      </div>
                      {(showAllSense || senseOpenIds.has(wp.id)) && (
                        <p className="wp-index-sense">{resolveSenseTitle(wp.sense_title)}</p>
                      )}
                      <div className="wp-index-detail-row">
                        <span className={`wp-visibility-pill ${wp.guest_public ? 'is-public' : 'is-private'}`}>
                          <MiniIcon name={wp.guest_public ? 'globe' : 'lock'} />
                          {wp.guest_public ? '公開中' : '非公開'}
                        </span>
                        <span className="wp-date-pill">
                          <MiniIcon name="calendar" />
                          {formatDate(wp.updated_at)}更新
                        </span>
                        <span className="wp-index-progress" aria-label="学習状況">
                          <span className="wp-progress-badge small learned">使える {wp.learned_count}</span>
                          <span className="wp-progress-badge small checked">確認済み {wp.checked_only_count}</span>
                        </span>
                      </div>
                    </div>
                    <div className="wp-index-actions">
                      <button
                        type="button"
                        className="wp-index-open-button"
                        onClick={() => openPreview(wp.id)}
                      >
                        <MiniIcon name="open" />開く
                      </button>
                      <button
                        id={`wp-action-trigger-${wp.id}`}
                        type="button"
                        className="wp-index-more"
                        aria-label={`${wp.lemma} のその他の操作`}
                        aria-haspopup="menu"
                        aria-expanded={actionMenuOpenId === wp.id}
                        aria-controls={`wp-action-menu-${wp.id}`}
                        onClick={() => {
                          toggleActionMenu(wp.id);
                        }}
                      >
                        <MiniIcon name="more" />
                        <span>その他</span>
                      </button>
                      {actionMenuOpenId === wp.id ? renderWordPackActionMenu(wp, 'list') : null}
                    </div>
                  </li>
                ))}
              </ul>
            )}

            {(hasPrev || hasNext) && (
              <div className="wp-pagination">
                <button
                  onClick={() => loadWordPacks(Math.max(0, offset - PAGE_LIMIT))}
                  disabled={!hasPrev || loading}
                >
                  前へ
                </button>
                <span>
                  {offset + 1}-{Math.min(offset + PAGE_LIMIT, total)} / {total}件
                </span>
                <button
                  onClick={() => loadWordPacks(offset + PAGE_LIMIT)}
                  disabled={!hasNext || loading}
                >
                  次へ
                </button>
              </div>
            )}
          </>
        ) : null}
      </div>
      <Modal
        isOpen={previewOpen} 
        onClose={closePreview}
        title={`WordPack プレビュー: ${previewMeta?.lemma ?? 'WordPack'}`}
        closeLabel="WordPackプレビューを閉じる"
      >
        {previewWordPackId ? (
          <div data-testid="modal-wordpack-content">
            <div className="wp-preview-nav" aria-label="Lexiconプレビューの文脈">
              <p className="wp-preview-nav__context">
                Lexiconの保存済み一覧から開いています。
              </p>
              {previewNavigationState ? (
                <div className="wp-preview-nav__actions" aria-label="プレビュー移動">
                  <button
                    type="button"
                    onClick={() => {
                      if (previewNavigationState.previousId) setPreviewWordPackId(previewNavigationState.previousId);
                    }}
                    disabled={!previewNavigationState.previousId}
                  >
                    前へ
                  </button>
                  <span className="wp-preview-nav__position">
                    {previewNavigationState.index + 1} / {previewNavigationState.total}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      if (previewNavigationState.nextId) setPreviewWordPackId(previewNavigationState.nextId);
                    }}
                    disabled={!previewNavigationState.nextId}
                  >
                    次へ
                  </button>
                </div>
              ) : null}
            </div>
            <WordPackPanel
              focusRef={modalFocusRef}
              selectedWordPackId={previewWordPackId}
              selectedMeta={previewMeta?.created_at && previewMeta?.updated_at ? { created_at: previewMeta.created_at, updated_at: previewMeta.updated_at } : null}
              fallbackMeta={previewMeta ? { id: previewMeta.id, lemma: previewMeta.lemma, senseTitle: previewMeta.senseTitle } : null}
              onWordPackGenerated={async () => {
                // 再生成後に一覧を最新化（更新日時の整合）
                await loadWordPacks(offset);
              }}
              onStudyProgressRecorded={applyStudyProgress}
              revealStudyCardImmediately
              onRequestClose={closePreview}
            />
          </div>
        ) : null}
      </Modal>
    </section>
  );
};
