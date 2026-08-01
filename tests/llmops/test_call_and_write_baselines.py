from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from backend.config import settings
from backend.flows.word_pack import WordPackFlow
from backend.infrastructure.firestore.repositories.app_store import AppFirestoreStore
from backend.models.word import ExampleCategory
from tests.firestore_fakes import FakeFirestoreClient

EXAMPLE_CATEGORIES = (
    ExampleCategory.Dev,
    ExampleCategory.CS,
    ExampleCategory.LLM,
    ExampleCategory.Business,
    ExampleCategory.Common,
)


class _SequencedWordPackLlm:
    def __init__(self, wordpack_payload: object) -> None:
        self.calls = 0
        self._wordpack_payload = wordpack_payload

    def complete(self, _prompt: str) -> str:
        self.calls += 1
        if self.calls == 1:
            return json.dumps(self._wordpack_payload, ensure_ascii=False)
        return json.dumps(
            {
                "examples": [
                    {
                        "en": "Teams converge on a practical plan today.",
                        "ja": "チームは今日、実用的な計画に収束する。",
                        "grammar_ja": "主語と動詞を持つ文です。",
                    },
                    {
                        "en": "The proposals converge after careful review.",
                        "ja": "提案は慎重なレビュー後に収束する。",
                        "grammar_ja": "自動詞 converge を使う文です。",
                    },
                ]
            },
            ensure_ascii=False,
        )


def _fixture() -> dict[str, object]:
    fixture = json.loads(
        Path("evals/fixtures/wordpack_converge.json").read_text(encoding="utf-8")
    )
    return fixture["wordpack"]


def test_wordpack_and_five_initial_example_categories_keep_six_call_baseline() -> None:
    llm = _SequencedWordPackLlm(_fixture())
    pack = WordPackFlow(
        llm=llm,
        llm_info={"model": "gpt-5.6-luna", "params": "reasoning.effort=high"},
    ).run("converge", pronunciation_enabled=False)

    assert llm.calls == 6
    assert len(pack.generation_provenance) == 6
    assert pack.generation_provenance[0]["validation"] == {
        "parse": True,
        "schema": True,
        "application": True,
    }
    for category in EXAMPLE_CATEGORIES:
        items = getattr(pack.examples, category.value)
        assert len(items) == 2
        assert all(len(item.generation_provenance) == 1 for item in items)


def test_wordpack_provenance_records_nested_schema_failure(monkeypatch) -> None:
    monkeypatch.setattr(settings, "strict_mode", False)
    llm = _SequencedWordPackLlm(
        {
            "senses": [{"id": "s1"}],
            "pronunciation": {"ipa_RP": "/test/"},
            "etymology": {"note": "test", "confidence": "low"},
            "study_card": "test",
        }
    )
    flow = WordPackFlow(llm=llm)

    result = flow._retrieve("converge")

    assert result["llm_data"] is not None
    assert flow.generation_provenance[0]["validation"] == {
        "parse": True,
        "schema": False,
        "application": False,
    }


def test_wordpack_strict_mode_rejects_schema_invalid_generated_payload(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "strict_mode", True)
    flow = WordPackFlow(
        llm=_SequencedWordPackLlm(
            {"senses": [{"id": "s1", "gloss_ja": "収束する"}]}
        )
    )

    with pytest.raises(RuntimeError, match="schema-valid usable data"):
        flow._retrieve("converge")


def test_wordpack_provenance_rejects_senses_with_only_blank_glosses(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "strict_mode", False)
    payload = _fixture()
    payload["senses"] = [
        {
            **payload["senses"][0],
            "gloss_ja": "   ",
        }
    ]
    flow = WordPackFlow(llm=_SequencedWordPackLlm(payload))

    result = flow._retrieve("converge")

    assert result["llm_data"] is not None
    assert flow.generation_provenance[0]["validation"] == {
        "parse": True,
        "schema": True,
        "application": False,
    }


def test_wordpack_provenance_records_non_object_json_schema_failure(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "strict_mode", False)
    flow = WordPackFlow(llm=_SequencedWordPackLlm([]))

    result = flow._retrieve("converge")

    assert result["llm_data"] == []
    assert flow.generation_provenance[0]["validation"] == {
        "parse": True,
        "schema": False,
        "application": False,
    }


def test_additional_example_generation_keeps_one_call_per_category() -> None:
    llm = _SequencedWordPackLlm(_fixture())
    llm.calls = 1
    generated = WordPackFlow(
        llm=llm,
        llm_info={"model": "gpt-5.6-luna", "params": "reasoning.effort=high"},
    ).generate_examples_for_categories("converge", {ExampleCategory.Dev: 2})

    assert llm.calls == 2
    assert len(generated[ExampleCategory.Dev]) == 2


def test_example_provenance_records_wrapper_and_row_schema_failures() -> None:
    class InvalidExampleLlm:
        def complete(self, _prompt: str) -> str:
            return json.dumps({"examples": [{"unexpected": "value"}]})

    flow = WordPackFlow(llm=InvalidExampleLlm())

    generated = flow.generate_examples_for_categories(
        "converge", {ExampleCategory.Dev: 1}
    )

    assert generated[ExampleCategory.Dev] == []
    assert flow.generation_provenance[0]["validation"] == {
        "parse": True,
        "schema": False,
        "application": False,
    }


def _wordpack_write_count(*, include_provenance: bool) -> tuple[int, set[str]]:
    client = FakeFirestoreClient()
    store = AppFirestoreStore(client=client)
    payload = deepcopy(_fixture())
    if not include_provenance:
        payload.pop("generation_provenance", None)
        for items in (payload.get("examples") or {}).values():
            for item in items:
                item.pop("generation_provenance", None)
    store.save_word_pack("wp:converge", "converge", json.dumps(payload, ensure_ascii=False))
    return len(client.write_log), set(client._data)


def _article_write_count(*, include_provenance: bool) -> tuple[int, set[str]]:
    client = FakeFirestoreClient()
    store = AppFirestoreStore(client=client)
    kwargs: dict[str, object] = {
        "title_en": "Convergence",
        "body_en": "Teams converge.",
        "body_ja": "チームは収束する。",
        "related_word_packs": [],
    }
    if include_provenance:
        kwargs["generation_provenance"] = [{"prompt_revision": "a" * 64}]
    store.save_article("article:converge", **kwargs)
    return len(client.write_log), set(client._data)


def _quiz_write_count(*, include_provenance: bool) -> tuple[int, set[str]]:
    client = FakeFirestoreClient()
    store = AppFirestoreStore(client=client)
    payload: dict[str, object] = {
        "title_en": "Convergence Quiz",
        "passages": [],
        "sections": [],
        "related_word_packs": [],
    }
    if include_provenance:
        payload["generation_provenance"] = [{"prompt_revision": "a" * 64}]
    store.save_quiz("quiz:converge", payload, [])
    return len(client.write_log), set(client._data)


def test_provenance_is_co_saved_without_extra_firestore_writes_or_collection() -> None:
    for counter in (_wordpack_write_count, _article_write_count, _quiz_write_count):
        baseline_count, baseline_collections = counter(include_provenance=False)
        provenance_count, provenance_collections = counter(include_provenance=True)
        assert provenance_count == baseline_count
        assert provenance_collections == baseline_collections
        assert not any("provenance" in name for name in provenance_collections)


def test_article_and_quiz_provenance_serialization_failure_keeps_primary_write() -> None:
    client = FakeFirestoreClient()
    store = AppFirestoreStore(client=client)

    store.save_article(
        "article:serialization-fallback",
        title_en="Fallback",
        body_en="The primary artifact remains available.",
        body_ja="主生成物は利用可能なままです。",
        generation_provenance=[object()],
    )
    store.save_quiz(
        "quiz:serialization-fallback",
        {
            "title_en": "Fallback",
            "passages": [],
            "sections": [],
            "related_word_packs": [],
            "generation_provenance": [object()],
        },
        [],
    )

    assert "article:serialization-fallback" in client._data["articles"]
    assert "quiz:serialization-fallback" in client._data["quizzes"]
