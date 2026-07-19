from __future__ import annotations

from fastapi import FastAPI

from backend.routers import word


def test_word_router_keeps_legacy_exports() -> None:
    """分割後も既存 tests / callers が差し替える公開属性を維持する。"""

    assert word.router is not None
    assert hasattr(word, "store")
    assert hasattr(word, "run_wordpack_flow")
    assert hasattr(word, "generate_word_pack_id")
    assert hasattr(word, "_regenerate_jobs")


def test_word_router_paths_are_registered_in_split_package() -> None:
    app = FastAPI()
    app.include_router(word.router)
    paths = set(app.openapi()["paths"])

    assert "/" in paths
    assert "/pack" in paths
    assert "/packs" in paths
    assert "/packs/{word_pack_id}" in paths
    assert "/packs/{word_pack_id}/regenerate" in paths
    assert "/packs/{word_pack_id}/regenerate/async" in paths
    assert "/packs/{word_pack_id}/examples/{category}/generate" in paths
    assert "/examples" in paths
    assert "/examples/bulk-delete" in paths
    assert "/lemma/{lemma}" in paths
