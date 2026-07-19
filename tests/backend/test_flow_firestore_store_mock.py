from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

# ルート（apps/backend 配下）を解決するためのパス追加。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))

from backend.flows import article_import as article_module
from backend.flows import category_generate_import as category_module
from backend.flows.article_import import ArticleImportFlow
from backend.flows.category_generate_import import CategoryGenerateAndImportFlow
from backend.models.word import ExampleCategory
from backend.store.firestore_store import AppFirestoreStore
from tests.firestore_fakes import FakeFirestoreClient


@pytest.fixture()
def firestore_store() -> AppFirestoreStore:
    """Firestore クライアントモックを介したストアを各テストに配布する。"""

    store = AppFirestoreStore(client=FakeFirestoreClient())
    store.wordpacks._word_packs.reset_query_log()
    return store


def test_category_flow_operates_with_firestore_store(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Firestore ストアを差し替えてもカテゴリー生成フローが完走することを検証する。"""

    monkeypatch.setattr(category_module, "store", firestore_store)
    monkeypatch.setattr(article_module, "store", firestore_store)

    dummy_llm = SimpleNamespace(complete=lambda prompt: "{}")
    monkeypatch.setattr(category_module, "get_llm_provider", lambda **_: dummy_llm)

    article_stub = SimpleNamespace(run=lambda req: SimpleNamespace(id="article-from-stub"))
    monkeypatch.setattr(category_module, "ArticleImportFlow", lambda **_: article_stub)

    class DummyCategoryFlow(CategoryGenerateAndImportFlow):
        """LLM 依存部を固定化したテスト専用フロー。"""

        def _choose_new_lemma(self, category: ExampleCategory) -> str:  # type: ignore[override]
            return "StreamSafe"

        def _generate_two_examples(  # type: ignore[override]
            self, lemma: str, category: ExampleCategory
        ) -> list[dict]:
            return [
                {"en": f"{lemma} example 1", "ja": "例1", "grammar_ja": "解説1"},
                {"en": f"{lemma} example 2", "ja": "例2", "grammar_ja": "解説2"},
            ]

    flow = DummyCategoryFlow()

    firestore_store.wordpacks._word_packs.reset_query_log()
    result = flow.run(ExampleCategory.Dev)

    assert result["lemma"] == "StreamSafe"
    assert firestore_store.list_examples(limit=10)

    log = firestore_store.wordpacks._word_packs.query_log
    assert any(("lemma_label_lower", "==", "streamsafe") in entry["filters"] for entry in log)


def test_article_import_flow_links_with_firestore_store(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ArticleImportFlow が Firestore ストア越しに WordPack を紐付けられることを確認する。"""

    monkeypatch.setattr(article_module, "store", firestore_store)

    firestore_store.save_word_pack(
        "wp-existing",
        "Latency",
        json.dumps({"lemma": "Latency", "examples": {}}, ensure_ascii=False),
    )
    firestore_store.wordpacks._word_packs.reset_query_log()

    class MinimalArticleImportFlow(ArticleImportFlow):
        """LLM を呼ばず、WordPack 紐付け部分のみを通す軽量フロー。"""

        def run(self, request: object) -> dict:  # type: ignore[override]
            lemmas = ["Latency", "Throughput"]
            links: list[tuple[str, str]] = []
            for lemma in lemmas:
                wp_id = article_module.store.find_word_pack_id_by_lemma(lemma)
                status = "existing"
                if wp_id is None:
                    wp_id = f"wp:{lemma}:demo"
                    payload = {"lemma": lemma, "sense_title": lemma, "examples": {}}
                    article_module.store.save_word_pack(
                        wp_id, lemma, json.dumps(payload, ensure_ascii=False)
                    )
                    status = "created"
                links.append((wp_id, status))
            return {"links": links}

    flow = MinimalArticleImportFlow()
    response = flow.run(SimpleNamespace(text="dummy"))

    assert response["links"][0][1] == "existing"
    assert response["links"][1][1] == "created"

    log = firestore_store.wordpacks._word_packs.query_log
    assert len(log) >= 2
    assert all(entry.get("limit") == 1 for entry in log if entry.get("filters"))
