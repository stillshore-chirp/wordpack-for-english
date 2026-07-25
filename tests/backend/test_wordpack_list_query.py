from __future__ import annotations

import pytest

from backend.application.wordpack.list_query import query_word_pack_rows
from backend.domain.wordpack.repositories import WordPackListFlagsTuple


def _row(
    index: int,
    *,
    lemma: str | None = None,
    public: bool = False,
    generated: bool = True,
    updated_at: str = "2026-07-24T00:00:00+00:00",
) -> WordPackListFlagsTuple:
    count = 1 if generated else 0
    return (
        f"wp:{index:03d}",
        lemma or f"lemma-{index:03d}",
        "一覧クエリテスト",
        "2026-07-01T00:00:00+00:00",
        updated_at,
        not generated,
        {"Dev": count, "CS": 0, "LLM": 0, "Business": 0, "Common": 0},
        0,
        0,
        public,
    )


@pytest.mark.parametrize(
    ("size", "first_page_size", "second_page_size"),
    [
        (199, 199, 0),
        (200, 200, 0),
        (201, 200, 1),
    ],
)
def test_query_slices_after_filtering_at_199_200_201_boundaries(
    size: int,
    first_page_size: int,
    second_page_size: int,
) -> None:
    rows = [_row(index) for index in range(size)]

    first_page = query_word_pack_rows(rows, limit=200, offset=0)
    second_page = query_word_pack_rows(rows, limit=200, offset=200)

    assert first_page.total == size
    assert first_page.filtered_total == size
    assert len(first_page.rows) == first_page_size
    assert len(second_page.rows) == second_page_size


def test_query_finds_a_match_that_was_previously_beyond_the_first_page() -> None:
    rows = [_row(index, public=False) for index in range(200)]
    rows.append(_row(200, lemma="later-page-only", public=True))

    result = query_word_pack_rows(
        rows,
        limit=200,
        offset=0,
        search="LATER-PAGE",
        search_mode="prefix",
        visibility="public",
    )

    assert result.total == 201
    assert result.filtered_total == 1
    assert [row[1] for row in result.rows] == ["later-page-only"]
    assert result.facet_counts.public == 1
    assert result.facet_counts.private == 0


def test_query_combines_search_visibility_generation_and_facets() -> None:
    rows = [
        _row(1, lemma="alpha-generated-public", public=True, generated=True),
        _row(2, lemma="alpha-empty-public", public=True, generated=False),
        _row(3, lemma="alpha-generated-private", public=False, generated=True),
        _row(4, lemma="bravo-generated-public", public=True, generated=True),
    ]

    result = query_word_pack_rows(
        rows,
        limit=200,
        offset=0,
        search="alpha",
        visibility="public",
        generation="generated",
        sort_key="lemma",
        sort_order="asc",
    )

    assert result.total == 4
    assert result.filtered_total == 1
    assert [row[1] for row in result.rows] == ["alpha-generated-public"]
    # 公開状態の候補件数は検索+生成条件を、生成状態の候補件数は検索+公開条件を保つ。
    assert result.facet_counts.public == 1
    assert result.facet_counts.private == 1
    assert result.facet_counts.generated == 1
    assert result.facet_counts.not_generated == 1


def test_query_returns_zero_without_losing_overall_total() -> None:
    result = query_word_pack_rows(
        [_row(1), _row(2)],
        limit=200,
        offset=0,
        search="missing",
    )

    assert result.total == 2
    assert result.filtered_total == 0
    assert result.rows == []
    assert result.facet_counts.public == 0
    assert result.facet_counts.private == 0
    assert result.facet_counts.generated == 0
    assert result.facet_counts.not_generated == 0


def test_query_uses_id_as_a_stable_tie_breaker_in_both_directions() -> None:
    rows = [_row(2), _row(1), _row(3)]

    ascending = query_word_pack_rows(
        rows,
        limit=200,
        offset=0,
        sort_key="updated_at",
        sort_order="asc",
    )
    descending = query_word_pack_rows(
        rows,
        limit=200,
        offset=0,
        sort_key="updated_at",
        sort_order="desc",
    )

    assert [row[0] for row in ascending.rows] == ["wp:001", "wp:002", "wp:003"]
    assert [row[0] for row in descending.rows] == ["wp:001", "wp:002", "wp:003"]
