import React from 'react';
import { sumExamples } from '../../features/wordpack/hooks/useWordPackList';
import { Badge, Button, EmptyState } from '../../shared/ui';
import type { WordPackListItem } from '../../features/wordpack/types';

interface ShelfWordPackListProps {
  items: WordPackListItem[];
  onOpenPreview: (wordPackId: string) => void;
  onClearSearch?: () => void;
  query?: string;
  queryMatchesShelf?: boolean;
}

const resolveSenseTitle = (wordPack: WordPackListItem): string =>
  wordPack.sense_title?.trim() || '語義タイトル未設定';

export const ShelfWordPackList: React.FC<ShelfWordPackListProps> = ({
  items,
  onOpenPreview,
  onClearSearch,
  query,
  queryMatchesShelf,
}) => {
  if (items.length === 0) {
    const filteredByQuery = Boolean(query && !queryMatchesShelf);
    return (
      <EmptyState>
        <div>
          <p>
            {filteredByQuery
              ? `「${query}」の条件で表示できるWordPackはこの棚にありません。`
              : 'この棚に入るWordPackはまだありません。'}
          </p>
          <p>
            {filteredByQuery
              ? '検索を解除すると、この棚のすべてのWordPackを確認できます。'
              : '別の棚を見るか、LexiconでWordPackを作成してください。'}
          </p>
          {onClearSearch ? (
            <Button variant="subtle" onClick={onClearSearch}>
              検索を解除
            </Button>
          ) : null}
        </div>
      </EmptyState>
    );
  }

  return (
    <ul className="shelf-wordpack-list" aria-label="棚内WordPack一覧">
      {items.map((wordPack) => (
        <li key={wordPack.id} className="shelf-wordpack-card">
          <div>
            <div className="dictionary-meta-row">
              {wordPack.is_empty ? (
                <Badge>例文未生成</Badge>
              ) : (
                <Badge>{sumExamples(wordPack.examples_count)}例文</Badge>
              )}
              {wordPack.guest_public ? <Badge variant="accent">ゲスト公開中</Badge> : null}
              <Badge>使える {wordPack.learned_count}</Badge>
              <Badge>確認済み {wordPack.checked_only_count}</Badge>
            </div>
            <h4>{wordPack.lemma}</h4>
            <p>{resolveSenseTitle(wordPack)}</p>
          </div>
          <Button
            variant="subtle"
            aria-label={`${wordPack.lemma}をプレビュー`}
            onClick={() => onOpenPreview(wordPack.id)}
          >
            プレビュー
          </Button>
        </li>
      ))}
    </ul>
  );
};
