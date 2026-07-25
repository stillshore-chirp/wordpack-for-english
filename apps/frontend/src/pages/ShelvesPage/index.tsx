import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { AppRightRail, RailCard } from '../../components/AppRightRail';
import { WordPackPreviewModal } from '../../components/WordPackPreviewModal';
import { useWordPackList } from '../../features/wordpack/hooks/useWordPackList';
import { Badge, Button, EmptyState, SearchBox } from '../../shared/ui';
import { ShelfWordPackList } from './ShelfWordPackList';
import { searchShelves } from './shelfSearch';
import { useSmartShelves } from './useSmartShelves';

export const ShelvesPage: React.FC = () => {
  const [query, setQuery] = useState('');
  const [activeShelfId, setActiveShelfId] = useState('recent');
  const [shelfOpenRequest, setShelfOpenRequest] = useState(0);
  const [selectionNotice, setSelectionNotice] = useState('');
  const [previewWordPackId, setPreviewWordPackId] = useState<string | null>(
    null,
  );
  const handledShelfOpenRequestRef = useRef(0);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const resultsHeadingRef = useRef<HTMLHeadingElement>(null);
  const {
    applyStudyProgress,
    hasLoaded,
    loading,
    message,
    partial,
    reload,
    total,
    wordPacks,
  } = useWordPackList({ loadAll: true });
  const shelves = useSmartShelves(wordPacks);
  const shelfResults = useMemo(
    () => searchShelves(shelves, query),
    [query, shelves],
  );
  const canShowShelves = hasLoaded && wordPacks.length > 0;
  const activeResult = canShowShelves
    ? shelfResults.find((result) => result.shelf.id === activeShelfId) ??
      shelfResults[0] ??
      null
    : null;
  const activeShelf = activeResult?.shelf ?? null;
  const activeItems = activeResult?.items ?? [];
  const hasQuery = query.trim().length > 0;
  const railBadge =
    activeShelf?.title ??
    (loading && !hasLoaded
      ? '読み込み中'
      : message && !hasLoaded
        ? '取得失敗'
        : hasLoaded && wordPacks.length === 0
          ? '保存なし'
          : hasQuery
            ? '検索結果なし'
            : '未選択');
  const railCopy = activeShelf
    ? '棚は自動分類です。WordPackの内容は変更せず、復習対象をまとめて表示します。'
    : loading && !hasLoaded
      ? '保存済みWordPackを取得しています。読み込み後に棚を選べます。'
      : message && !hasLoaded
        ? '棚を表示できません。接続を確認して一覧を再読み込みしてください。'
        : hasLoaded && wordPacks.length === 0
          ? 'Lexiconで見出し語を保存すると、自動分類の棚が表示されます。'
          : '検索を解除すると、自動分類の棚とWordPack一覧へ戻れます。';

  useEffect(() => {
    if (!canShowShelves || shelfResults.length === 0) return;
    if (!shelfResults.some((result) => result.shelf.id === activeShelfId)) {
      setActiveShelfId(shelfResults[0].shelf.id);
    }
  }, [activeShelfId, canShowShelves, shelfResults]);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      if (
        !(event.metaKey || event.ctrlKey) ||
        event.key.toLowerCase() !== 'k' ||
        document.querySelector('[role="dialog"][aria-modal="true"]')
      ) {
        return;
      }
      event.preventDefault();
      searchInputRef.current?.focus();
      searchInputRef.current?.select();
    };
    window.addEventListener('keydown', focusSearch);
    return () => window.removeEventListener('keydown', focusSearch);
  }, []);

  useEffect(() => {
    if (
      shelfOpenRequest === 0 ||
      shelfOpenRequest === handledShelfOpenRequestRef.current ||
      !activeShelf
    ) {
      return;
    }
    const heading = resultsHeadingRef.current;
    if (!heading) return;
    handledShelfOpenRequestRef.current = shelfOpenRequest;
    heading.focus({ preventScroll: true });
    const reduceMotion = window.matchMedia?.(
      '(prefers-reduced-motion: reduce)',
    ).matches;
    heading.scrollIntoView({
      behavior: reduceMotion ? 'auto' : 'smooth',
      block: 'start',
    });
    setSelectionNotice(
      `${activeShelf.title}のWordPackを${activeItems.length}件表示しました。`,
    );
  }, [activeItems.length, activeShelf, shelfOpenRequest]);

  const openShelf = useCallback((shelfId: string) => {
    setActiveShelfId(shelfId);
    setShelfOpenRequest((request) => request + 1);
  }, []);

  const clearSearch = useCallback(() => {
    setQuery('');
    searchInputRef.current?.focus();
  }, []);

  return (
    <div className="dictionary-main">
      <div className="dictionary-workspace">
        <div className="dictionary-primary">
          <div className="dictionary-page-heading">
            <div className="dictionary-page-title">
              <h2>Shelves</h2>
              <p>
                保存済みWordPackを条件別に自動分類し、復習する束を選びます。
              </p>
            </div>
            <div className="dictionary-top-actions">
              <SearchBox
                ref={searchInputRef}
                label="棚とWordPackを検索"
                placeholder="棚名、見出し語、語義で検索"
                shortcut="⌘/Ctrl K"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
              <Button
                variant="subtle"
                onClick={() => {
                  void reload();
                }}
                disabled={loading}
              >
                {loading ? '更新中' : '更新'}
              </Button>
            </div>
          </div>
          <section className="dictionary-section">
            <div className="dictionary-section-header">
              <div>
                <h3>自動分類の棚</h3>
                <p>
                  保存済みWordPackを復習目的ごとにまとめます。WordPackの内容は変更しません。
                </p>
              </div>
              {hasLoaded ? (
                <Badge variant="accent">保存済み{total}件</Badge>
              ) : null}
            </div>
            {loading && !hasLoaded ? (
              <EmptyState role="status" aria-live="polite">
                保存済みWordPackを読み込んでいます…
              </EmptyState>
            ) : null}
            {message && !hasLoaded ? (
              <EmptyState role="alert">
                <div>
                  <p>
                    {message.text}
                    。棚を表示できません。接続を確認して、もう一度お試しください。
                  </p>
                  <Button variant="subtle" onClick={() => void reload()}>
                    一覧を再読み込み
                  </Button>
                </div>
              </EmptyState>
            ) : null}
            {message && hasLoaded && partial ? (
              <div role="alert" className="dictionary-empty compact">
                <p>
                  {message.text}。全{total}件のうち{wordPacks.length}
                  件を取得し、表示中の件数だけで棚を分類しています。
                </p>
                <Button variant="subtle" onClick={() => void reload()}>
                  全件を再読み込み
                </Button>
              </div>
            ) : null}
            {message && hasLoaded && !partial ? (
              <div role="alert" className="dictionary-empty compact">
                <p>
                  {message.text}
                  。前回取得した{wordPacks.length}件を表示しています。
                </p>
                <Button variant="subtle" onClick={() => void reload()}>
                  もう一度更新
                </Button>
              </div>
            ) : null}
            {loading && hasLoaded ? (
              <p role="status" aria-live="polite" className="dictionary-status-copy">
                一覧を更新中です。現在の{wordPacks.length}件を表示しています。
              </p>
            ) : null}
            {partial && hasLoaded && !message ? (
              <div role="alert" className="dictionary-empty compact">
                全{total}件のうち{wordPacks.length}
                件を取得しました。表示中の件数だけで棚を分類しています。
                <Button variant="subtle" onClick={() => void reload()}>
                  全件を再読み込み
                </Button>
              </div>
            ) : null}
            {hasLoaded && !message && wordPacks.length === 0 ? (
              <EmptyState>
                <div>
                  <p>保存済みWordPackはまだありません。</p>
                  <p>Lexiconで見出し語を保存すると、自動分類の棚が表示されます。</p>
                  <a className="dictionary-button subtle" href="/lexicon">
                    Lexiconを開く
                  </a>
                </div>
              </EmptyState>
            ) : null}
            {canShowShelves && shelfResults.length === 0 ? (
              <EmptyState role="status" aria-live="polite">
                <div>
                  <p>「{query.trim()}」に一致する棚やWordPackはありません。</p>
                  <p>検索語を短くするか、検索を解除してください。</p>
                  <Button variant="subtle" onClick={clearSearch}>
                    検索を解除
                  </Button>
                </div>
              </EmptyState>
            ) : null}
            {canShowShelves && shelfResults.length > 0 ? (
              <ul className="shelf-grid" aria-label="自動分類の棚一覧">
                {shelfResults.map((result) => {
                  const { shelf } = result;
                  const isActive = activeShelf?.id === shelf.id;
                  const countLabel =
                    hasQuery && !result.matchedByShelf
                      ? `${result.items.length}件一致 / 全${shelf.items.length}件`
                      : `${shelf.items.length}件`;
                  return (
                    <li key={shelf.id}>
                      <article
                        className={`shelf-card ${shelf.accent}`}
                        data-selected={isActive ? 'true' : undefined}
                      >
                        <h4>{shelf.title}</h4>
                        <p>{shelf.description}</p>
                        <div className="shelf-card-footer">
                          <div className="shelf-card-summary">
                            <span>{countLabel}</span>
                            {isActive ? (
                              <Badge variant="accent">選択中</Badge>
                            ) : null}
                          </div>
                          <Button
                            variant="subtle"
                            aria-controls="shelves-results"
                            aria-label={`「${shelf.title}」棚のWordPack一覧${
                              isActive ? 'へ移動' : 'を表示'
                            }`}
                            aria-pressed={isActive}
                            onClick={() => openShelf(shelf.id)}
                          >
                            {isActive ? '一覧へ移動' : 'この棚を表示'}
                          </Button>
                        </div>
                      </article>
                    </li>
                  );
                })}
              </ul>
            ) : null}
          </section>
          {activeShelf && canShowShelves ? (
            <section
              id="shelves-results"
              className="dictionary-section shelves-results"
              aria-labelledby="shelves-results-heading"
            >
              <div className="dictionary-section-header">
                <div>
                  <h3
                    id="shelves-results-heading"
                    ref={resultsHeadingRef}
                    className="shelves-results-heading"
                    tabIndex={-1}
                  >
                    {activeShelf.title}
                  </h3>
                  <p>{activeShelf.description}</p>
                </div>
                <Badge variant="accent">{activeItems.length}件表示</Badge>
              </div>
              <ShelfWordPackList
                items={activeItems}
                query={hasQuery ? query.trim() : undefined}
                onOpenPreview={setPreviewWordPackId}
                onClearSearch={hasQuery ? clearSearch : undefined}
              />
              <p
                className="visually-hidden"
                role="status"
                aria-live="polite"
                aria-atomic="true"
              >
                {selectionNotice}
              </p>
            </section>
          ) : null}
        </div>
        <AppRightRail>
          <RailCard title="現在の棚" badge={railBadge}>
            {hasLoaded ? (
              <div className="dictionary-rail-metrics" aria-label="棚の集計">
                <span>
                  <strong>{total}</strong>保存済み
                </span>
                <span>
                  <strong>{activeItems.length}</strong>表示中
                </span>
              </div>
            ) : null}
            <p className="dictionary-rail-copy">{railCopy}</p>
          </RailCard>
        </AppRightRail>
      </div>
      <WordPackPreviewModal
        isOpen={Boolean(previewWordPackId)}
        onClose={() => setPreviewWordPackId(null)}
        wordPackId={previewWordPackId}
        wordPacks={wordPacks}
        contextLabel={`Shelves / ${activeShelf?.title ?? '棚'}`}
        contextDescription={`${activeShelf?.title ?? '選択中の棚'}から開いています。復習対象を棚の中で前後に確認できます。`}
        navigationIds={activeItems.map((item) => item.id)}
        onNavigate={setPreviewWordPackId}
        onWordPackUpdated={() => {
          void reload();
        }}
        onStudyProgressRecorded={applyStudyProgress}
      />
    </div>
  );
};
