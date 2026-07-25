import { sumExamples } from '../../features/wordpack/hooks/useWordPackList';
import type { ExampleCategory, WordPackListItem } from '../../features/wordpack/types';

export type SmartShelfAccent = 'sky' | 'yellow' | 'rose' | 'green' | 'purple' | 'gold';

export interface SmartShelf {
  id: string;
  title: string;
  description: string;
  accent: SmartShelfAccent;
  items: WordPackListItem[];
}

const byUpdatedAtDesc = (a: WordPackListItem, b: WordPackListItem): number =>
  new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();

const byExampleCountDesc = (a: WordPackListItem, b: WordPackListItem): number =>
  sumExamples(b.examples_count) - sumExamples(a.examples_count);

const hasCategoryExamples = (wordPack: WordPackListItem, category: ExampleCategory): boolean =>
  (wordPack.examples_count?.[category] ?? 0) > 0;

const missingSenseTitle = (wordPack: WordPackListItem): boolean => {
  const value = (wordPack.sense_title ?? '').trim().toLowerCase();
  return !value || value === 'fallback' || value === '語義タイトル未設定';
};

export const buildSmartShelves = (wordPacks: WordPackListItem[]): SmartShelf[] => {
  const sortedByUpdatedAt = [...wordPacks].sort(byUpdatedAtDesc);
  const manyExamples = [...wordPacks]
    .filter((wordPack) => sumExamples(wordPack.examples_count) >= 5)
    .sort(byExampleCountDesc);

  return [
    {
      id: 'recent',
      title: '最近更新',
      description: '更新日時の新しいWordPack',
      accent: 'sky',
      items: sortedByUpdatedAt.slice(0, 30),
    },
    {
      id: 'empty',
      title: '未生成',
      description: '例文をまだ生成していないWordPack',
      accent: 'rose',
      items: wordPacks.filter((wordPack) => wordPack.is_empty),
    },
    {
      id: 'many-examples',
      title: '例文が多い',
      description: '合計5件以上の例文を持つWordPack',
      accent: 'green',
      items: manyExamples,
    },
    {
      id: 'learned',
      title: '学習済みあり',
      description: '「使える」と記録したWordPack',
      accent: 'purple',
      items: wordPacks.filter((wordPack) => wordPack.learned_count > 0).sort(byUpdatedAtDesc),
    },
    {
      id: 'checked-only',
      title: '確認だけ多め',
      description: '確認数が学習済み数を上回るWordPack',
      accent: 'yellow',
      items: wordPacks
        .filter((wordPack) => wordPack.checked_only_count > wordPack.learned_count)
        .sort(byUpdatedAtDesc),
    },
    {
      id: 'guest-public',
      title: 'ゲスト公開中',
      description: 'ゲスト閲覧で公開しているWordPack',
      accent: 'gold',
      items: wordPacks.filter((wordPack) => wordPack.guest_public).sort(byUpdatedAtDesc),
    },
    {
      id: 'sense-missing',
      title: '語義未設定',
      description: '語義タイトルをまだ設定していないWordPack',
      accent: 'rose',
      items: wordPacks.filter(missingSenseTitle).sort(byUpdatedAtDesc),
    },
    {
      id: 'dev',
      title: 'Dev語彙',
      description: 'Dev例文を持つWordPack',
      accent: 'green',
      items: wordPacks.filter((wordPack) => hasCategoryExamples(wordPack, 'Dev')).sort(byUpdatedAtDesc),
    },
    {
      id: 'business',
      title: 'Business語彙',
      description: 'Business例文を持つWordPack',
      accent: 'purple',
      items: wordPacks.filter((wordPack) => hasCategoryExamples(wordPack, 'Business')).sort(byUpdatedAtDesc),
    },
    {
      id: 'common',
      title: 'Common語彙',
      description: 'Common例文を持つWordPack',
      accent: 'sky',
      items: wordPacks.filter((wordPack) => hasCategoryExamples(wordPack, 'Common')).sort(byUpdatedAtDesc),
    },
  ];
};
