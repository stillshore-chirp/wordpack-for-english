import type { WordPackListItem } from '../../features/wordpack/types';
import type { SmartShelf } from './smartShelfRules';

export interface ShelfSearchResult {
  items: WordPackListItem[];
  matchedByShelf: boolean;
  shelf: SmartShelf;
}

const includesQuery = (value: string | null | undefined, query: string): boolean =>
  (value ?? '').toLocaleLowerCase().includes(query);

export const normalizeShelfQuery = (query: string): string =>
  query.trim().toLocaleLowerCase();

export const searchShelves = (
  shelves: SmartShelf[],
  query: string,
): ShelfSearchResult[] => {
  const normalizedQuery = normalizeShelfQuery(query);
  if (!normalizedQuery) {
    return shelves.map((shelf) => ({
      items: shelf.items,
      matchedByShelf: false,
      shelf,
    }));
  }

  return shelves.flatMap((shelf) => {
    const matchedByShelf =
      includesQuery(shelf.title, normalizedQuery) ||
      includesQuery(shelf.description, normalizedQuery);
    const matchingItems = shelf.items.filter(
      (wordPack) =>
        includesQuery(wordPack.lemma, normalizedQuery) ||
        includesQuery(wordPack.sense_title, normalizedQuery),
    );

    if (!matchedByShelf && matchingItems.length === 0) return [];
    return [{
      items: matchedByShelf ? shelf.items : matchingItems,
      matchedByShelf,
      shelf,
    }];
  });
};
