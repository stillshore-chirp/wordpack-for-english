import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { formatDateJst } from '../lib/date';
import { useSettings } from '../SettingsContext';
import { useModal } from '../ModalContext';
import { useConfirmDialog } from '../ConfirmDialogContext';
import { fetchJson, ApiError } from '../lib/fetcher';
import { useNotifications } from '../NotificationsContext';
import { regenerateWordPackRequest } from '../lib/wordpack';
import { Modal } from './Modal';
import ArticleDetailModal, { ArticleDetailData } from './ArticleDetailModal';
import { useAbortableAsync, AbortError } from '../lib/hooks';
import { assignSetValues, retainSetValues, toggleSetValue } from '../lib/set';
import { useAuth } from '../AuthContext';
import { GuestLock } from './GuestLock';
import { APP_EVENTS, dispatchAppEvent } from '../shared/events/appEvents';

interface ArticleListItem {
  id: string;
  title_en: string;
  created_at: string;
  updated_at: string;
  guest_public?: boolean;
}

interface ArticleListResponse {
  items: ArticleListItem[];
  total: number;
  limit: number;
  offset: number;
}

type ArticleDetailResponse = ArticleDetailData;

const LIST_LIMIT = 20;

export const ArticleListPanel: React.FC = () => {
  const { isGuest } = useAuth();
  const { settings } = useSettings();
  const { setModalOpen } = useModal();
  const { add: addNotification, update: updateNotification } = useNotifications();
  const confirmDialog = useConfirmDialog();
  const [loading, setLoading] = useState(false);
  const [items, setItems] = useState<ArticleListItem[]>([]);
  const [msg, setMsg] = useState<{ kind: 'status' | 'alert'; text: string } | null>(null);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [preview, setPreview] = useState<ArticleDetailResponse | null>(null);
  const [wpPreviewId, setWpPreviewId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const { run: runAbortable } = useAbortableAsync();

  // 一覧の取得は useAbortableAsync で逐次キャンセルし、古いリクエストの結果が後勝ちしないようにする。
  const load = useCallback(
    async (newOffset = 0) => {
      setLoading(true);
      setMsg(null);
      try {
        const res = await runAbortable((signal) =>
          fetchJson<ArticleListResponse>(
            `${settings.apiBase}/article?limit=${LIST_LIMIT}&offset=${newOffset}`,
            { signal },
          ),
        );
        setItems(res.items.map((item) => ({ ...item, guest_public: item.guest_public ?? false })));
        setTotal(res.total);
        setOffset((prev) => (prev === newOffset ? prev : newOffset));
      } catch (e) {
        if (e instanceof AbortError) {
          return;
        }
        const m = e instanceof ApiError ? e.message : '文章一覧の読み込みに失敗しました';
        setMsg({ kind: 'alert', text: m });
      } finally {
        setLoading(false);
      }
    },
    [runAbortable, settings.apiBase],
  );

  useEffect(() => {
    setSelectedIds((prev) => {
      if (prev.size === 0) return prev;
      const next = retainSetValues(prev, items.map((it) => it.id));
      return next.size === prev.size ? prev : next;
    });
  }, [items]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => toggleSetValue(prev, id));
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const allVisibleSelected = useMemo(
    () => items.length > 0 && items.every((it) => selectedIds.has(it.id)),
    [items, selectedIds],
  );

  const toggleVisibleSelection = useCallback(() => {
    setSelectedIds((prev) => assignSetValues(prev, items.map((it) => it.id), !allVisibleSelected));
  }, [allVisibleSelected, items]);

  const open = async (id: string) => {
    setLoading(true);
    setMsg(null);
    try {
      const res = await fetchJson<ArticleDetailResponse>(`${settings.apiBase}/article/${id}`);
      setPreview(res);
      setWpPreviewId(null);
      setPreviewOpen(true);
      try { setModalOpen(true); } catch {}
    } catch (e) {
      const m = e instanceof ApiError ? e.message : '文章の取得に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  };

  const del = async (item: ArticleListItem) => {
    const targetLabel = item.title_en?.trim() || '文章';
    const confirmed = await confirmDialog(targetLabel);
    if (!confirmed) return;
    setLoading(true);
    setMsg(null);
    try {
      await fetchJson(`${settings.apiBase}/article/${item.id}`, { method: 'DELETE' });
      await load(offset);
      setSelectedIds((prev) => (prev.has(item.id) ? toggleSetValue(prev, item.id) : prev));
      setMsg({ kind: 'status', text: '削除しました' });
    } catch (e) {
      const m = e instanceof ApiError ? e.message : '削除に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  };

  const toggleArticleGuestPublic = async (item: ArticleListItem) => {
    if (isGuest) return;
    const previous = Boolean(item.guest_public);
    const nextValue = !previous;
    setItems((prev) => prev.map((article) => (
      article.id === item.id ? { ...article, guest_public: nextValue } : article
    )));
    setPreview((prev) => (
      prev?.id === item.id ? { ...prev, guest_public: nextValue } : prev
    ));
    try {
      const response = await fetchJson<{ article_id: string; guest_public: boolean }>(
        `${settings.apiBase}/article/${encodeURIComponent(item.id)}/guest-public`,
        {
          method: 'POST',
          body: { guest_public: nextValue },
        },
      );
      setItems((prev) => prev.map((article) => (
        article.id === item.id ? { ...article, guest_public: response.guest_public } : article
      )));
      setPreview((prev) => (
        prev?.id === item.id ? { ...prev, guest_public: response.guest_public } : prev
      ));
      setMsg({
        kind: 'status',
        text: response.guest_public ? 'Reader記事をゲスト公開しました' : 'Reader記事を非公開にしました',
      });
    } catch (e) {
      setItems((prev) => prev.map((article) => (
        article.id === item.id ? { ...article, guest_public: previous } : article
      )));
      setPreview((prev) => (
        prev?.id === item.id ? { ...prev, guest_public: previous } : prev
      ));
      const m = e instanceof ApiError ? e.message : 'Reader記事の公開設定を更新できませんでした';
      setMsg({ kind: 'alert', text: m });
    }
  };

  const deleteWordPack = async (wordPackId: string) => {
    if (!preview) return;
    const lemmaLabel = (() => {
      try { return preview.related_word_packs.find((l) => l.word_pack_id === wordPackId)?.lemma?.trim(); }
      catch { return undefined; }
    })();
    const confirmed = await confirmDialog(lemmaLabel || 'WordPack');
    if (!confirmed) return;
    setLoading(true);
    setMsg(null);
    try {
      await fetchJson(`${settings.apiBase}/word/packs/${wordPackId}`, { method: 'DELETE' });
      const refreshed = await fetchJson<ArticleDetailResponse>(`${settings.apiBase}/article/${preview.id}`);
      setPreview(refreshed);
      setMsg({ kind: 'status', text: 'WordPackを削除しました' });
      dispatchAppEvent(APP_EVENTS.wordPackUpdated);
    } catch (e) {
      const m = e instanceof ApiError ? e.message : 'WordPackの削除に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  };

  const regenerateWordPack = async (wordPackId: string) => {
    if (!preview) return;
    setLoading(true);
    setMsg(null);
    const lemma = (() => {
      try { return preview.related_word_packs.find((l) => l.word_pack_id === wordPackId)?.lemma || 'WordPack'; } catch { return 'WordPack'; }
    })();
    const ctrl = new AbortController();
    try {
      await regenerateWordPackRequest({
        apiBase: settings.apiBase,
        wordPackId,
        settings: {
          pronunciationEnabled: settings.pronunciationEnabled,
          regenerateScope: settings.regenerateScope,
          requestTimeoutMs: settings.requestTimeoutMs,
          generationRequestTimeoutMs: settings.generationRequestTimeoutMs,
          reasoningEffort: settings.reasoningEffort,
          textVerbosity: settings.textVerbosity,
        },
        // 設定からモデルを渡す（未設定ならサーバ既定に委ねる）
        model: settings.model,
        lemma,
        notify: { add: addNotification, update: updateNotification },
        abortSignal: ctrl.signal,
        messages: {
          progress: 'WordPackを再生成しています',
          success: '再生成が完了しました',
          failure: undefined, // ApiError.message を優先
        },
      });
      const refreshed = await fetchJson<ArticleDetailResponse>(`${settings.apiBase}/article/${preview.id}`);
      setPreview(refreshed);
      setMsg({ kind: 'status', text: 'WordPackを再生成しました' });
    } catch (e) {
      const m = e instanceof ApiError ? e.message : 'WordPackの再生成に失敗しました';
      setMsg({ kind: 'alert', text: m });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load(0);
  }, [load]);
  // インポート完了などで記事が更新されたら、現在のオフセットで再読込
  useEffect(() => {
    const onUpdated = () => {
      load(offset);
    };
    try { window.addEventListener('article:updated', onUpdated as EventListener); } catch {}
    return () => {
      try { window.removeEventListener('article:updated', onUpdated as EventListener); } catch {}
    };
  }, [load, offset]);

  const hasNext = offset + LIST_LIMIT < total;
  const hasPrev = offset > 0;
  const selectedCount = selectedIds.size;
  const showGlobalEmpty = items.length === 0 && !loading && total === 0;
  const showPageEmpty = items.length === 0 && !loading && total > 0;

  const deleteSelectedArticles = useCallback(async () => {
    if (selectedIds.size === 0) return;
    const ids = Array.from(selectedIds);
    const confirmed = await confirmDialog(`選択中の文章（${ids.length}件）`);
    if (!confirmed) return;
    setLoading(true);
    setMsg(null);
    let deleted = 0;
    let failure: string | null = null;
    try {
      for (const id of ids) {
        try {
          await fetchJson(`${settings.apiBase}/article/${id}`, { method: 'DELETE' });
          deleted += 1;
        } catch (error) {
          const message = error instanceof ApiError ? error.message : '削除に失敗しました';
          failure = message;
          break;
        }
      }
      if (deleted > 0) {
        await load(offset);
        clearSelection();
      }
      if (failure) {
        const text = deleted > 0
          ? `文章を${deleted}件削除しましたが一部失敗しました: ${failure}`
          : `文章の削除に失敗しました: ${failure}`;
        setMsg({ kind: 'alert', text });
      } else if (deleted > 0) {
        setMsg({ kind: 'status', text: `文章を${deleted}件削除しました` });
      } else {
        setMsg({ kind: 'alert', text: '削除対象がありません' });
      }
    } finally {
      setLoading(false);
    }
  }, [clearSelection, confirmDialog, load, offset, selectedIds, settings.apiBase]);

  return (
    <section>
      <style>{`
        .al-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 0.5rem; }
        .al-card { border: 1px solid var(--color-border); border-radius: 8px; padding: 0.5rem; background: var(--color-surface); cursor: pointer; }
        .al-card-header { display: flex; align-items: center; gap: 0.5rem; }
        .al-card-title-row { display: flex; align-items: center; gap: 0.5rem; flex: 1; }
        .al-public-row { display: flex; align-items: center; gap: 0.45rem; flex-wrap: wrap; margin-top: 0.45rem; }
        .al-public-pill { display: inline-flex; align-items: center; min-height: 1.6rem; padding: 0.15rem 0.5rem; border: 1px solid #cbd5e1; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }
        .al-public-pill.is-public { border-color: #86efac; background: #f0fdf4; color: #166534; }
        .al-public-pill.is-private { background: #f8fafc; color: #475569; }
        .al-public-button { min-height: 2.3rem; padding: 0.3rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; background: #ffffff; color: #0f172a; cursor: pointer; }
        .al-empty-state { padding: 1.25rem; border: 1px dashed var(--color-border); border-radius: 8px; color: var(--color-subtle); background: var(--color-surface); }
        .al-empty-state strong { display: block; color: inherit; margin-bottom: 0.25rem; }
        .al-list-header { display: flex; align-items: center; justify-content: space-between; }
        .al-pagination { display: flex; justify-content: center; gap: 8px; margin-top: 8px; }
        .al-list-header > button,
        .al-card-title-row button,
        .al-public-button,
        .al-pagination button {
          padding: 0.25rem 0.75rem;
          border: 1px solid #cbd5e1;
          border-radius: 4px;
          background: #ffffff;
          color: #0f172a;
          cursor: pointer;
        }
        .al-list-header > button:hover:not(:disabled),
        .al-card-title-row button:hover:not(:disabled),
        .al-public-button:hover:not(:disabled),
        .al-pagination button:hover:not(:disabled) {
          background: #f8fafc;
        }
        .al-public-button:focus-visible {
          outline: 3px solid rgba(37, 99, 235, 0.35);
          outline-offset: 2px;
        }
        .al-list-header > button:disabled,
        .al-card-title-row button:disabled,
        .al-public-button:disabled,
        .al-pagination button:disabled {
          background: #e5e7eb;
          color: #374151;
          cursor: not-allowed;
        }
        .wp-selection-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 0.5rem; margin: 0.75rem 0; font-size: 0.9em; }
        .wp-selection-bar button { padding: 0.25rem 0.75rem; border: 1px solid #cbd5e1; border-radius: 4px; background: #ffffff; color: #0f172a; cursor: pointer; }
        .wp-selection-bar button:disabled { background: #e5e7eb; color: #374151; cursor: not-allowed; }
        .wp-select-checkbox { display: inline-flex; align-items: center; justify-content: center; }
        .wp-select-checkbox input { width: 1rem; height: 1rem; cursor: pointer; }
      `}</style>
      <div className="al-list-header">
        <h2>インポート済み文章</h2>
        <button onClick={() => load(offset)} disabled={loading}>更新</button>
      </div>
      {msg && <div role={msg.kind}>{msg.text}</div>}
      <div className="wp-selection-bar" role="group" aria-label="文章選択操作">
        <span>選択中: {selectedCount}件</span>
        {/* 選択UIは削除と直結するため、ゲスト時はロックする */}
        <GuestLock isGuest={isGuest}>
          <button type="button" onClick={toggleVisibleSelection} disabled={items.length === 0}>
            {allVisibleSelected ? '表示中を選択解除' : '表示中を全選択'}
          </button>
        </GuestLock>
        <GuestLock isGuest={isGuest}>
          <button type="button" onClick={clearSelection} disabled={selectedCount === 0}>
            全選択解除
          </button>
        </GuestLock>
        <GuestLock isGuest={isGuest}>
          <button
            type="button"
            onClick={deleteSelectedArticles}
            disabled={selectedCount === 0 || loading}
          >選択した文章を削除</button>
        </GuestLock>
      </div>
      <div className="al-grid">
        {items.map((it) => (
          <div key={it.id} className="al-card" onClick={() => open(it.id)}>
            <div className="al-card-header">
              <label className="wp-select-checkbox" onClick={(e) => e.stopPropagation()}>
                <GuestLock isGuest={isGuest}>
                  <input
                    type="checkbox"
                    checked={selectedIds.has(it.id)}
                    onChange={() => toggleSelect(it.id)}
                    aria-label={`文章 ${it.title_en} を選択`}
                  />
                </GuestLock>
              </label>
              <div className="al-card-title-row">
                <strong style={{ flex: 1, fontSize: '12px' }}>{it.title_en}</strong>
                <GuestLock isGuest={isGuest}>
                  <button onClick={(e) => { e.stopPropagation(); del(it); }} aria-label={`delete-article-${it.id}`}>削除</button>
                </GuestLock>
              </div>
            </div>
            <div className="al-public-row">
              <span className={`al-public-pill ${it.guest_public ? 'is-public' : 'is-private'}`}>
                {it.guest_public ? '公開中' : '非公開'}
              </span>
              {!isGuest ? (
                <button
                  type="button"
                  className="al-public-button"
                  onClick={(e) => {
                    e.stopPropagation();
                    void toggleArticleGuestPublic(it);
                  }}
                >
                  {it.guest_public ? '非公開にする' : '公開にする'}
                </button>
              ) : null}
            </div>
            <div style={{ fontSize: '10px', color: 'var(--color-subtle)' }}>更新: {formatDateJst(it.updated_at)}</div>
          </div>
        ))}
      </div>
      {showGlobalEmpty ? (
        <div className="al-empty-state">
          <strong>{isGuest ? 'ゲスト公開中のReader記事はまだありません。' : 'インポート済み文章はまだありません。'}</strong>
          <span>
            {isGuest
              ? 'ログイン済みユーザーが公開したReader記事だけがここに表示されます。'
              : '文章をインポートすると、ここから本文と関連WordPackを開けます。'}
          </span>
        </div>
      ) : null}
      {showPageEmpty ? (
        <div className="al-empty-state">
          <strong>{isGuest ? 'このページに表示できるゲスト公開Reader記事がありません。' : 'このページに表示できるReader記事がありません。'}</strong>
          <span>前のページへ戻ると、残っているReader記事を確認できます。</span>
          <button
            type="button"
            className="al-public-button"
            onClick={() => load(Math.max(0, offset - LIST_LIMIT))}
            disabled={!hasPrev || loading}
          >
            前のページへ戻る
          </button>
        </div>
      ) : null}
      {(hasPrev || hasNext) && (
        <div className="al-pagination">
          <button onClick={() => load(offset - LIST_LIMIT)} disabled={!hasPrev || loading}>前へ</button>
          <span>{offset + 1}-{Math.min(offset + LIST_LIMIT, total)} / {total}件</span>
          <button onClick={() => load(offset + LIST_LIMIT)} disabled={!hasNext || loading}>次へ</button>
        </div>
      )}

      <ArticleDetailModal
        isOpen={previewOpen}
        onClose={() => { setPreviewOpen(false); setWpPreviewId(null); try { setModalOpen(false); } catch {} }}
        article={preview}
        title="文章プレビュー"
        onRegenerateWordPack={regenerateWordPack}
        previewWordPackId={wpPreviewId}
        onSelectWordPackPreview={setWpPreviewId}
        onDeleteWordPack={deleteWordPack}
        onWordPackGenerated={async () => {
          if (preview) {
            const refreshed = await fetchJson<ArticleDetailResponse>(`${settings.apiBase}/article/${preview.id}`);
            setPreview(refreshed);
          }
          dispatchAppEvent(APP_EVENTS.wordPackUpdated);
        }}
      />
    </section>
  );
};
