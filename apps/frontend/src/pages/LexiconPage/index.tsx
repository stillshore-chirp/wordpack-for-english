import React from 'react';
import { WordPackPanel } from '../../components/WordPackPanel';
import { WordPackListPanel } from '../../components/WordPackListPanel';
import { AppRightRail } from '../../components/AppRightRail';
import { Button } from '../../shared/ui';
import './lexicon.css';

interface LexiconPageProps {
  focusRef: React.RefObject<HTMLElement>;
  selectedWordPackId: string | null;
  onWordPackGenerated: (wordPackId: string | null) => void;
}

export const LexiconPage: React.FC<LexiconPageProps> = ({
  focusRef,
  onWordPackGenerated,
}) => {
  const [topSearch, setTopSearch] = React.useState('');
  const topSearchRef = React.useRef<HTMLInputElement>(null);

  const focusCreateInput = React.useCallback(() => {
    try { focusRef.current?.focus(); } catch {}
  }, [focusRef]);

  const applyTopSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      window.dispatchEvent(new CustomEvent('wordpack:list-search', {
        detail: { mode: 'contains', value: topSearch },
      }));
    } catch {}
  };

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        topSearchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  React.useEffect(() => {
    const handleCreateFocus = () => focusCreateInput();
    const handleSearchCleared = () => setTopSearch('');
    const handleSearchSynced = (event: Event) => {
      const detail = (event as CustomEvent<{ value?: string }>).detail;
      setTopSearch(detail?.value ?? '');
    };
    window.addEventListener('wordpack:create-focus', handleCreateFocus);
    window.addEventListener('wordpack:list-search-cleared', handleSearchCleared);
    window.addEventListener('wordpack:list-search-synced', handleSearchSynced);
    return () => {
      window.removeEventListener('wordpack:create-focus', handleCreateFocus);
      window.removeEventListener('wordpack:list-search-cleared', handleSearchCleared);
      window.removeEventListener('wordpack:list-search-synced', handleSearchSynced);
    };
  }, [focusCreateInput]);

  return (
    <div className="dictionary-main lexicon-main">
      <div className="dictionary-workspace lexicon-workspace">
        <div className="dictionary-primary lexicon-primary">
          <div className="dictionary-page-heading lexicon-page-heading">
            <div className="dictionary-page-title">
              <h2>Lexicon</h2>
              <p>保存済みの個人辞書を検索・管理します。</p>
            </div>
            <div className="dictionary-top-actions lexicon-top-actions">
              <form className="lexicon-searchbar" role="search" aria-label="保存済みWordPackを検索" onSubmit={applyTopSearch}>
                <span className="lexicon-searchbar__icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    <circle cx="11" cy="11" r="6.5" />
                    <path d="m16 16 4 4" />
                  </svg>
                </span>
                <label className="visually-hidden" htmlFor="lexicon-top-search">保存済みWordPackを検索</label>
                <input
                  id="lexicon-top-search"
                  ref={topSearchRef}
                  type="search"
                  value={topSearch}
                  onChange={(event) => setTopSearch(event.target.value)}
                  placeholder="保存済みWordPackを検索"
                />
                <kbd aria-hidden="true">⌘ K</kbd>
              </form>
              <Button variant="primary" className="lexicon-create-shortcut" onClick={focusCreateInput}>
                <span aria-hidden="true">＋</span>
                新しいWordPack
              </Button>
            </div>
          </div>

          <section className="dictionary-section lexicon-list-section" aria-label="保存済みWordPack一覧 セクション">
            <WordPackListPanel />
          </section>
        </div>

        <AppRightRail>
          <WordPackPanel
            focusRef={focusRef}
            onWordPackGenerated={onWordPackGenerated}
            creationPanelPlacement="inline"
            showDetails={false}
          />
        </AppRightRail>
      </div>
    </div>
  );
};
