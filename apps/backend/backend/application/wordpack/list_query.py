from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ...domain.wordpack.repositories import WordPackListFlagsTuple

WordPackSearchMode = Literal["prefix", "suffix", "contains"]
WordPackVisibilityFilter = Literal["all", "public", "private"]
WordPackGenerationFilter = Literal["all", "generated", "not_generated"]
WordPackSortKey = Literal["created_at", "updated_at", "lemma", "total_examples"]
WordPackSortOrder = Literal["asc", "desc"]


@dataclass(frozen=True)
class WordPackFacetCounts:
    """Counts for each alternate facet value across the current server-side scope."""

    public: int
    private: int
    generated: int
    not_generated: int


@dataclass(frozen=True)
class WordPackListQueryResult:
    rows: list[WordPackListFlagsTuple]
    total: int
    filtered_total: int
    facet_counts: WordPackFacetCounts


def _total_examples(row: WordPackListFlagsTuple) -> int:
    return sum(max(0, int(value)) for value in row[6].values())


def _matches_search(
    row: WordPackListFlagsTuple,
    *,
    search: str,
    search_mode: WordPackSearchMode,
) -> bool:
    query = search.strip().casefold()
    if not query:
        return True
    lemma = row[1].casefold()
    if search_mode == "prefix":
        return lemma.startswith(query)
    if search_mode == "suffix":
        return lemma.endswith(query)
    return query in lemma


def _matches_visibility(
    row: WordPackListFlagsTuple,
    visibility: WordPackVisibilityFilter,
) -> bool:
    if visibility == "public":
        return row[9]
    if visibility == "private":
        return not row[9]
    return True


def _matches_generation(
    row: WordPackListFlagsTuple,
    generation: WordPackGenerationFilter,
) -> bool:
    if generation == "generated":
        return _total_examples(row) > 0
    if generation == "not_generated":
        return _total_examples(row) == 0
    return True


def _sort_rows(
    rows: list[WordPackListFlagsTuple],
    *,
    sort_key: WordPackSortKey,
    sort_order: WordPackSortOrder,
) -> list[WordPackListFlagsTuple]:
    # ID を先に安定順へ揃えることで、同じ日時・lemma・例文数でもページ境界が揺れない。
    stable_rows = sorted(rows, key=lambda row: row[0].casefold())
    if sort_key == "lemma":
        key = lambda row: row[1].casefold()
    elif sort_key == "total_examples":
        key = _total_examples
    elif sort_key == "created_at":
        key = lambda row: row[3]
    else:
        key = lambda row: row[4]
    return sorted(stable_rows, key=key, reverse=sort_order == "desc")


def query_word_pack_rows(
    rows: list[WordPackListFlagsTuple],
    *,
    limit: int,
    offset: int,
    search: str = "",
    search_mode: WordPackSearchMode = "contains",
    visibility: WordPackVisibilityFilter = "all",
    generation: WordPackGenerationFilter = "all",
    sort_key: WordPackSortKey = "created_at",
    sort_order: WordPackSortOrder = "desc",
) -> WordPackListQueryResult:
    """Apply all list conditions before slicing the requested page."""

    search_rows = [
        row
        for row in rows
        if _matches_search(row, search=search, search_mode=search_mode)
    ]
    visibility_facet_rows = [
        row for row in search_rows if _matches_generation(row, generation)
    ]
    generation_facet_rows = [
        row for row in search_rows if _matches_visibility(row, visibility)
    ]
    filtered_rows = [
        row
        for row in search_rows
        if _matches_visibility(row, visibility)
        and _matches_generation(row, generation)
    ]
    ordered_rows = _sort_rows(
        filtered_rows,
        sort_key=sort_key,
        sort_order=sort_order,
    )
    normalized_offset = max(0, int(offset))
    normalized_limit = max(0, int(limit))
    page_rows = ordered_rows[
        normalized_offset : normalized_offset + normalized_limit
    ]

    return WordPackListQueryResult(
        rows=page_rows,
        total=len(rows),
        filtered_total=len(filtered_rows),
        facet_counts=WordPackFacetCounts(
            public=sum(1 for row in visibility_facet_rows if row[9]),
            private=sum(1 for row in visibility_facet_rows if not row[9]),
            generated=sum(
                1 for row in generation_facet_rows if _total_examples(row) > 0
            ),
            not_generated=sum(
                1 for row in generation_facet_rows if _total_examples(row) == 0
            ),
        ),
    )
