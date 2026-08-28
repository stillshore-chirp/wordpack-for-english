import React from 'react';
import { WordPackPanel } from '../../components/WordPackPanel';
import { WordPackListPanel } from '../../components/WordPackListPanel';
import { AppRightRail } from '../../components/AppRightRail';
import { WORDPACK_SEARCH_MAX_LENGTH } from '../../features/wordpack/types';
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
  const [topSearchError, setTopSearchError] = React.useState<string | null>(null);
  const topSearchRef = React.useRef<HTMLInputElement>(null);

  const focusCreateInput = () => {
    try { focusRef.current?.focus(); } catch {}
  };

  const applyTopSearch = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = topSearch.trim();
    if (value.length > WORDPACK_SEARCH_MAX_LENGTH) {
      setTopSearchError(`検索語は${WORDPACK_SEARCH_MAX_LENGTH}文字以内で入力してください。`);
      topSearchRef.current?.focus();
      return;
    }
    setTopSearchError(null);
    try {
      window.dispatchEvent(new CustomEvent('wordpack:list-search', {
        detail: { mode: 'contains', value },
      }));
    } catch {}
  };

  React.useEffect(() => {
    const handleSearchSynced = (event: Event) => {
      const detail = (event as CustomEvent<{ value?: string }>).detail;
      setTopSearch((detail?.value ?? '').trim());
      setTopSearchError(null);
    };
    const handleSearchCleared = () => {
      setTopSearch('');
      setTopSearchError(null);
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        topSearchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('wordpack:list-search-synced', handleSearchSynced);
    window.addEventListener('wordpack:list-search-cleared', handleSearchCleared);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('wordpack:list-search-synced', handleSearchSynced);
      window.removeEventListener('wordpack:list-search-cleared', handleSearchCleared);
    };
  }, []);

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
              <form
                className={`lexicon-searchbar${topSearchError ? ' lexicon-searchbar--invalid' : ''}`}
                role="search"
                aria-label="保存済みWordPackを検索"
                onSubmit={applyTopSearch}
              >
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
                  onChange={(event) => {
                    const value = event.target.value;
                    setTopSearch(value);
                    if (value.trim().length <= WORDPACK_SEARCH_MAX_LENGTH) setTopSearchError(null);
                  }}
                  placeholder="保存済みWordPackを検索"
                  aria-invalid={topSearchError ? 'true' : undefined}
                  aria-describedby={topSearchError ? 'lexicon-top-search-error' : undefined}
                />
                <kbd aria-hidden="true">⌘ K</kbd>
                {topSearchError ? (
                  <span id="lexicon-top-search-error" className="lexicon-searchbar__error" role="alert">
                    {topSearchError}
                  </span>
                ) : null}
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
