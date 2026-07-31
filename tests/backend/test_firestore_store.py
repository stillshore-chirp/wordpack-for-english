from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from typing import Any

import uuid

import pytest
from google.api_core import exceptions as gexc
from google.cloud import firestore
from structlog.testing import capture_logs

# ルート（apps/backend 配下）をテストから直接解決できるようにする。
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "apps" / "backend"))
import backend.store.firestore_store as firestore_module
from tests.firestore_fakes import (
    FakeAggregationQuery,
    FakeAggregationResult,
    FakeCollectionReference,
    FakeDocumentReference,
    FakeDocumentSnapshot,
    FakeFirestoreClient,
    FakeQuery,
    FakeWriteBatch,
    FakeTransaction,
)

AppFirestoreStore = firestore_module.AppFirestoreStore
if not hasattr(firestore_module, "FakeQuery"):
    firestore_module.FakeQuery = FakeQuery  # type: ignore[attr-defined]

@pytest.fixture()
def firestore_store() -> AppFirestoreStore:
    return AppFirestoreStore(client=FakeFirestoreClient())


def test_firestore_repository_import_paths_and_composition() -> None:
    from backend.infrastructure.firestore.repositories import (
        AppFirestoreRepository,
        FirestoreArticleRepository,
        FirestoreExampleRepository,
        FirestoreQuizRepository,
        FirestoreRegenerateJobRepository,
        FirestoreUserRepository,
        FirestoreWordPackRepository,
    )
    from backend.store import AppFirestoreStore as StorePackageAppFirestoreStore
    from backend.store.firestore_store import (
        AppFirestoreStore as LegacyAppFirestoreStore,
        FirestoreArticleStore,
        FirestoreBaseStore,
        FirestoreExampleStore,
        FirestoreQuizStore,
        FirestoreRegenerateJobStore,
        FirestoreUserStore,
        FirestoreWordPackStore,
    )

    assert StorePackageAppFirestoreStore is LegacyAppFirestoreStore
    assert issubclass(FirestoreWordPackStore, FirestoreBaseStore)
    assert issubclass(FirestoreWordPackStore, FirestoreWordPackRepository)
    assert issubclass(FirestoreExampleStore, FirestoreExampleRepository)
    assert issubclass(FirestoreArticleStore, FirestoreArticleRepository)
    assert issubclass(FirestoreQuizStore, FirestoreQuizRepository)
    assert issubclass(FirestoreUserStore, FirestoreUserRepository)
    assert issubclass(FirestoreRegenerateJobStore, FirestoreRegenerateJobRepository)

    legacy_store = LegacyAppFirestoreStore(client=FakeFirestoreClient())
    assert isinstance(legacy_store.users, FirestoreUserStore)
    assert isinstance(legacy_store.wordpacks, FirestoreWordPackStore)
    assert isinstance(legacy_store.examples, FirestoreExampleStore)
    assert isinstance(legacy_store.articles, FirestoreArticleStore)
    assert isinstance(legacy_store.quizzes, FirestoreQuizStore)
    assert isinstance(legacy_store.regenerate_jobs, FirestoreRegenerateJobStore)

    repository_store = AppFirestoreRepository(client=FakeFirestoreClient())
    assert type(repository_store.users) is FirestoreUserRepository
    assert type(repository_store.wordpacks) is FirestoreWordPackRepository
    assert type(repository_store.examples) is FirestoreExampleRepository
    assert type(repository_store.articles) is FirestoreArticleRepository
    assert type(repository_store.quizzes) is FirestoreQuizRepository
    assert type(repository_store.regenerate_jobs) is FirestoreRegenerateJobRepository


def test_firestore_regenerate_job_roundtrip(firestore_store: AppFirestoreStore) -> None:
    created = firestore_store.create_regenerate_job(
        job_id="job-1",
        word_pack_id="wp:demo",
    )

    assert created["job_id"] == "job-1"
    assert created["word_pack_id"] == "wp:demo"
    assert created["status"] == "pending"
    assert created["error"] is None

    running = firestore_store.update_regenerate_job("job-1", status="running")
    assert running is not None
    assert running["status"] == "running"

    succeeded = firestore_store.update_regenerate_job(
        "job-1",
        status="succeeded",
        result_json='{"lemma":"demo"}',
    )
    assert succeeded is not None
    assert succeeded["status"] == "succeeded"
    assert succeeded["result_json"] == '{"lemma":"demo"}'

    failed = firestore_store.update_regenerate_job("job-1", status="failed", error="timeout")
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error"] == "timeout"

    found = firestore_store.get_regenerate_job("job-1")
    assert found is not None
    assert found["word_pack_id"] == "wp:demo"
    assert firestore_store.get_regenerate_job("missing") is None


def test_firestore_article_import_job_roundtrip(firestore_store: AppFirestoreStore) -> None:
    created = firestore_store.create_article_import_job(
        job_id="article-import-job:demo",
        owner_user_id="user-1",
    )

    assert created["job_id"] == "article-import-job:demo"
    assert created["owner_user_id"] == "user-1"
    assert created["status"] == "queued"
    assert created["article_id"] is None

    running = firestore_store.update_article_import_job(
        "article-import-job:demo",
        status="running",
    )
    assert running is not None
    assert running["status"] == "running"

    succeeded = firestore_store.update_article_import_job(
        "article-import-job:demo",
        status="succeeded",
        article_id="art:demo",
    )
    assert succeeded is not None
    assert succeeded["article_id"] == "art:demo"

    found = firestore_store.get_article_import_job("article-import-job:demo")
    assert found is not None
    assert found["owner_user_id"] == "user-1"
    assert firestore_store.get_article_import_job("missing") is None


def test_firestore_quiz_generation_job_roundtrip(firestore_store: AppFirestoreStore) -> None:
    created = firestore_store.create_quiz_generation_job(job_id="quiz-job:demo")

    assert created["job_id"] == "quiz-job:demo"
    assert created["status"] == "queued"
    assert created["quiz_id"] is None
    assert created["error"] is None

    running = firestore_store.update_quiz_generation_job("quiz-job:demo", status="running")
    assert running is not None
    assert running["status"] == "running"

    succeeded = firestore_store.update_quiz_generation_job(
        "quiz-job:demo",
        status="succeeded",
        quiz_id="quiz:demo",
        result_json='{"id":"quiz:demo"}',
    )
    assert succeeded is not None
    assert succeeded["status"] == "succeeded"
    assert succeeded["quiz_id"] == "quiz:demo"
    assert succeeded["result_json"] == '{"id":"quiz:demo"}'

    failed = firestore_store.update_quiz_generation_job(
        "quiz-job:demo",
        status="failed",
        error="timeout",
    )
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["error"] == "timeout"

    found = firestore_store.get_quiz_generation_job("quiz-job:demo")
    assert found is not None
    assert found["job_id"] == "quiz-job:demo"
    assert firestore_store.get_quiz_generation_job("missing") is None


def test_firestore_quiz_roundtrip_and_attempt_cleanup(firestore_store: AppFirestoreStore) -> None:
    quiz_payload = {
        "id": "quiz:test",
        "title_en": "Reliable API Deployments",
        "format_profile": "single_passage",
        "generation_domain": "technical",
        "domain_intensity": "standard",
        "difficulty": "medium",
        "passages": [
            {
                "id": "p1",
                "order": 1,
                "kind": "article",
                "title": "Deployment review",
                "body_en": "Teams mitigate latency by adding a fallback.",
                "body_ja": "チームはフォールバックを追加してレイテンシを軽減する。",
                "speaker_labels": [],
            }
        ],
        "notes_ja": "根拠を本文から確認します。",
        "sections": [
            {
                "id": "s1",
                "order": 1,
                "title": "Reading",
                "description_ja": "本文理解",
                "passage_ids": ["p1"],
                "questions": [
                    {
                        "id": "q1",
                        "order": 1,
                        "type": "detail",
                        "prompt": "What reduces latency?",
                        "choices": [
                            {"id": "A", "text": "A fallback"},
                            {"id": "B", "text": "A redesign"},
                            {"id": "C", "text": "A delay"},
                            {"id": "D", "text": "A meeting"},
                        ],
                        "correct_choice_id": "A",
                        "explanation": {
                            "explanation_ja": "fallback が latency を軽減する根拠です。",
                            "evidence_passage_id": "p1",
                            "evidence_text": "mitigate latency by adding a fallback",
                            "evidence_start": 6,
                            "evidence_end": 43,
                            "wrong_choice_explanations_ja": {},
                            "related_lemmas": ["mitigate", "latency", "fallback"],
                        },
                    }
                ],
            }
        ],
        "related_word_packs": [
            {
                "word_pack_id": "wp:mitigate",
                "lemma": "mitigate",
                "status": "existing",
                "is_empty": False,
                "occurrences": [{"passage_id": "p1", "start": 6, "end": 14}],
                "warning": None,
            }
        ],
        "source_word_pack_ids": ["wp:mitigate"],
        "source_lemmas": ["mitigate"],
        "topic_seed": "API deploy",
        "avoid_topics": [],
        "llm_model": "gpt-5.4-mini",
        "llm_params": "reasoning.effort=minimal;text.verbosity=medium",
        "guest_public": True,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-02T00:00:00+00:00",
    }

    firestore_store.save_quiz(
        "quiz:test",
        quiz_payload,
        quiz_payload["related_word_packs"],
    )

    stored = firestore_store.get_quiz("quiz:test")
    assert stored is not None
    assert stored["title_en"] == "Reliable API Deployments"
    assert stored["passages"][0]["body_en"].startswith("Teams mitigate")
    assert stored["related_word_packs"][0]["lemma"] == "mitigate"
    assert firestore_store.count_quizzes(public_only=True) == 1
    assert firestore_store.list_quizzes(public_only=True)[0]["id"] == "quiz:test"

    firestore_store.save_quiz_attempt(
        "attempt:test",
        {
            "quiz_id": "quiz:test",
            "answers": [{"question_id": "q1", "selected_choice_id": "A"}],
            "results": [
                {
                    "question_id": "q1",
                    "selected_choice_id": "A",
                    "correct_choice_id": "A",
                    "is_correct": True,
                }
            ],
            "score": 1,
            "total": 1,
            "percentage": 100.0,
            "submitted_at": "2024-01-02T00:00:00+00:00",
            "created_at": "2024-01-02T00:00:00+00:00",
        },
    )

    attempts = firestore_store.list_quiz_attempts("quiz:test")
    assert attempts[0]["score"] == 1
    assert firestore_store.delete_quiz("quiz:test") is True
    assert firestore_store.get_quiz("quiz:test") is None
    assert firestore_store.list_quiz_attempts("quiz:test") == []


def test_firestore_word_pack_roundtrip(firestore_store: AppFirestoreStore) -> None:
    payload = {
        "lemma": "Converge",
        "sense_title": "まとまる",
        "examples": {
            "Dev": [
                {"en": "Converge the commits", "ja": "コミットをまとめる", "checked_only_count": 2},
                {"en": "Signals converge", "ja": "信号が収束する"},
            ]
        },
    }
    firestore_store.save_word_pack("wp-1", payload["lemma"], json.dumps(payload, ensure_ascii=False))

    stored = firestore_store.get_word_pack("wp-1")
    assert stored is not None
    lemma, data_json, created_at, updated_at = stored
    assert lemma == "Converge"
    assert created_at <= updated_at
    data = json.loads(data_json)
    assert data["examples"]["Dev"][0]["en"] == "Converge the commits"
    assert data["examples"]["Dev"][0]["checked_only_count"] == 2


def test_firestore_word_pack_accepts_uuid_style_ids(
    firestore_store: AppFirestoreStore,
) -> None:
    payload = {"lemma": "UuidCase", "examples": {"Dev": []}}
    wp_id = f"wp:{uuid.uuid4().hex}"

    firestore_store.save_word_pack(wp_id, payload["lemma"], json.dumps(payload, ensure_ascii=False))

    stored = firestore_store.get_word_pack(wp_id)
    assert stored is not None
    lemma, _, _, _ = stored
    assert lemma == payload["lemma"]


def test_firestore_example_progress_and_deletion(firestore_store: AppFirestoreStore) -> None:
    payload = {
        "lemma": "Refine",
        "examples": {
            "Dev": [{"en": "Refine the UI", "ja": "UIを磨く"}],
            "CS": [{"en": "Refine search", "ja": "検索精度を上げる"}],
        },
    }
    firestore_store.save_word_pack("wp-2", payload["lemma"], json.dumps(payload, ensure_ascii=False))
    listed = firestore_store.list_examples(limit=10)
    assert len(listed) == 2
    first_example_id = listed[0][0]

    pack_id, next_checked, next_learned = firestore_store.update_example_study_progress(
        first_example_id, 3, 1
    )
    assert pack_id == "wp-2"
    assert next_checked == 3
    assert next_learned == 1

    remaining = firestore_store.delete_example("wp-2", "Dev", 0)
    assert remaining == 0
    counts = firestore_store.wordpacks.list_word_packs_with_flags(limit=1)[0][6]
    assert counts["Dev"] == 0
    assert counts["CS"] == 1


def test_contains_search_prefers_specific_term(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {
        "lemma": "Chunk",
        "examples": {
            "Dev": [
                {"en": "Analyze xyz value", "ja": "xyzの値を分析する"},
            ]
        },
    }
    firestore_store.save_word_pack(
        "wp-search", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    firestore_store.examples._examples.reset_query_log()
    firestore_store.list_examples(search="yz", search_mode="contains")

    filters = firestore_store.examples._examples.query_log[0]["filters"]
    assert ("search_terms", "array_contains", "yz") in filters


def test_list_word_packs_paginates_via_firestore_query(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    timestamps = iter(
        [
            "2024-01-01T00:00:01+00:00",
            "2024-01-01T00:00:02+00:00",
            "2024-01-01T00:00:03+00:00",
        ]
    )
    monkeypatch.setattr(firestore_module, "_now_iso", lambda: next(timestamps))

    for idx, lemma in enumerate(["Alpha", "Beta", "Gamma"], start=1):
        firestore_store.save_word_pack(
            f"wp-{idx}",
            lemma,
            json.dumps({"lemma": lemma, "examples": {}}, ensure_ascii=False),
        )

    first_page = firestore_store.list_word_packs(limit=2, offset=0)
    assert [row[1] for row in first_page] == ["Gamma", "Beta"]

    second_page = firestore_store.list_word_packs(limit=2, offset=2)
    assert [row[1] for row in second_page] == ["Alpha"]

    flagged_page = firestore_store.list_word_packs_with_flags(limit=1, offset=1)
    assert [row[1] for row in flagged_page] == ["Beta"]


def test_count_word_packs_uses_server_side_aggregation(
    firestore_store: AppFirestoreStore,
) -> None:
    for idx, lemma in enumerate(["Delta", "Echo"], start=1):
        firestore_store.save_word_pack(
            f"pack-{idx}",
            lemma,
            json.dumps({"lemma": lemma, "examples": {}}, ensure_ascii=False),
        )

    total = firestore_store.count_word_packs()
    assert total == 2
    assert firestore_store.wordpacks._word_packs.count_calls == 1


def test_extract_count_from_aggregation_accepts_sdk_value_tuple() -> None:
    """本番 SDK の count 結果がネストした value 形でも件数を拾える。"""

    aggregation = [[SimpleNamespace(value=130)]]

    assert firestore_module._extract_count_from_aggregation(aggregation) == 130


def test_extract_count_from_aggregation_accepts_non_count_alias() -> None:
    """Firestore SDK が count 以外の alias で返しても単一値なら件数として扱う。"""

    aggregation = [SimpleNamespace(aggregate_fields={"field_1": 130})]

    assert firestore_module._extract_count_from_aggregation(aggregation) == 130


def test_has_guest_demo_word_pack_uses_metadata_filter(
    firestore_store: AppFirestoreStore,
) -> None:
    payload = {"lemma": "GuestDemo", "examples": {}}
    firestore_store.save_word_pack(
        "wp-guest",
        payload["lemma"],
        json.dumps(payload, ensure_ascii=False),
        metadata={"guest_demo": True},
    )

    collection = firestore_store.wordpacks._word_packs
    collection.reset_query_log()

    assert firestore_store.has_guest_demo_word_pack() is True

    log = collection.query_log
    assert len(log) == 1
    assert ("metadata.guest_demo", "==", True) in log[0]["filters"]
    assert log[0]["limit"] == 1


def test_list_public_word_packs_filters_by_guest_public(
    firestore_store: AppFirestoreStore,
) -> None:
    payload = {"lemma": "Public", "examples": {}}
    firestore_store.save_word_pack(
        "wp-public",
        payload["lemma"],
        json.dumps(payload, ensure_ascii=False),
        metadata={"guest_public": True},
    )
    firestore_store.save_word_pack(
        "wp-private",
        "Private",
        json.dumps({"lemma": "Private", "examples": {}}, ensure_ascii=False),
    )

    public_rows = firestore_store.list_public_word_packs_with_flags(limit=10, offset=0)
    assert [row[0] for row in public_rows] == ["wp-public"]
    assert public_rows[0][-1] is True
    assert firestore_store.count_public_word_packs() == 1


def test_find_word_pack_lookup_uses_filtered_query(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """lemma 検索が limit(1) 付きのフィルタクエリになることを確認する。"""

    timestamps = iter(
        [
            "2024-05-01T10:00:00+00:00",
            "2024-05-02T11:00:00+00:00",
        ]
    )
    monkeypatch.setattr(firestore_module, "_now_iso", lambda: next(timestamps))

    payload = {"lemma": "LemmaX", "sense_title": "x", "examples": {}}
    firestore_store.save_word_pack(
        "wp-old", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    payload_new = {"lemma": "lemmax", "sense_title": "new", "examples": {}}
    firestore_store.save_word_pack(
        "wp-new", payload_new["lemma"], json.dumps(payload_new, ensure_ascii=False)
    )

    collection = firestore_store.wordpacks._word_packs
    collection.reset_query_log()

    result = firestore_store.find_word_pack_id_by_lemma("  LEMMAX  ")

    assert result == "wp-new"
    log = collection.query_log
    assert len(log) == 1
    assert ("lemma_label_lower", "==", "lemmax") in log[0]["filters"]
    assert log[0]["limit"] == 1
    assert log[0]["size"] == 1


def test_find_word_pack_lookup_retries_after_google_api_error(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GoogleAPIError を補足してリトライする挙動を固定する。"""

    payload = {"lemma": "Resilient", "sense_title": "x", "examples": {}}
    firestore_store.save_word_pack(
        "wp-stable", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    original_stream = FakeQuery.stream
    attempts = {"count": 0}

    def flaky_stream(self):  # type: ignore[override]
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise gexc.GoogleAPIError("transient")
        return original_stream(self)

    monkeypatch.setattr(FakeQuery, "stream", flaky_stream)

    with capture_logs() as cap:
        result = firestore_store.find_word_pack_id_by_lemma("resilient")

    assert result == "wp-stable"
    assert attempts["count"] == 2
    retry_logs = [entry for entry in cap if entry.get("event") == "firestore_wordpack_lookup_retry"]
    assert retry_logs
    assert retry_logs[0].get("attempt") == 1


def test_find_word_pack_lookup_returns_none_after_retries(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GoogleAPIError が連続した場合は None を返してログを残す。"""

    def failing_stream(self):  # type: ignore[override]
        raise gexc.GoogleAPIError("permanent failure")

    monkeypatch.setattr(firestore_module.FakeQuery, "stream", failing_stream)

    with capture_logs() as cap:
        result = firestore_store.find_word_pack_id_by_lemma("unstable")

    assert result is None
    failure_logs = [entry for entry in cap if entry.get("event") == "firestore_wordpack_lookup_give_up"]
    assert failure_logs


def test_allocate_example_ids_handles_generator_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeFirestoreClient()
    firestore_store = AppFirestoreStore(client=client)

    class GeneratorTransaction(FakeTransaction):
        def get(self, doc_ref):  # type: ignore[override]
            snapshot = super().get(doc_ref)

            def _gen():
                yield snapshot

            return _gen()

    monkeypatch.setattr(client, "transaction", lambda: GeneratorTransaction(client))

    ids = firestore_store.wordpacks._allocate_example_ids(3)  # pylint: disable=protected-access

    assert ids == [1, 2, 3]


def test_allocate_example_ids_falls_back_on_transaction_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Firestore がトランザクションを拒否した場合でも採番が継続することを保証する。"""

    client = FakeFirestoreClient()
    firestore_store = AppFirestoreStore(client=client)

    class BrokenTransaction(FakeTransaction):
        def get(self, doc_ref):  # type: ignore[override]
            raise ValueError("Transaction not in progress, cannot be used in API requests.")

    monkeypatch.setattr(client, "transaction", lambda: BrokenTransaction(client))

    with capture_logs() as cap:
        ids = firestore_store.wordpacks._allocate_example_ids(2)  # pylint: disable=protected-access

    assert ids == [1, 2]
    events = [entry.get("event") for entry in cap]
    assert "firestore_allocate_ids_transaction_failed" in events


def test_find_word_pack_with_metadata_uses_filtered_query(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """find_word_pack_by_lemma_ci もフィルタ + limit で絞り込むことを検証する。"""

    timestamps = iter(
        [
            "2024-06-01T09:00:00+00:00",
            "2024-06-02T10:00:00+00:00",
        ]
    )
    monkeypatch.setattr(firestore_module, "_now_iso", lambda: next(timestamps))

    payload = {"lemma": "Resilient", "sense_title": "old", "examples": {}}
    firestore_store.save_word_pack(
        "wp-first", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    payload_new = {"lemma": "resilient", "sense_title": "latest", "examples": {}}
    firestore_store.save_word_pack(
        "wp-second", payload_new["lemma"], json.dumps(payload_new, ensure_ascii=False)
    )

    collection = firestore_store.wordpacks._word_packs
    collection.reset_query_log()

    found = firestore_store.find_word_pack_by_lemma_ci("resilient")

    assert found is not None
    assert found[0] == "wp-second"
    assert found[1].lower() == "resilient"
    assert len(collection.query_log) == 1
    entry = collection.query_log[0]
    assert ("lemma_label_lower", "==", "resilient") in entry["filters"]
    assert entry["limit"] == 1
    assert entry["size"] == 1


def test_store_factory_switches_to_firestore(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.store as store_module

    monkeypatch.setattr(store_module.settings, "environment", "production")

    sentinel = object()
    monkeypatch.setattr(store_module, "AppFirestoreStore", lambda **_: sentinel)
    new_store = store_module._create_store()
    assert new_store is sentinel


def test_example_queries_limit_scanned_documents(
    firestore_store: AppFirestoreStore,
) -> None:
    """大量データ下でも対象パックの件数だけを走査することを検証する。"""

    categories = ["Dev", "CS"]
    per_category = 10
    for idx in range(1, 16):
        lemma = f"Lemma-{idx}"
        payload = {
            "lemma": lemma,
            "examples": {
                cat: [
                    {"en": f"{cat} example {idx}-{n}", "ja": f"{cat} ja {idx}-{n}"}
                    for n in range(per_category)
                ]
                for cat in categories
            },
        }
        firestore_store.save_word_pack(
            f"mass-{idx}", lemma, json.dumps(payload, ensure_ascii=False)
        )

    target_pack = "mass-3"
    collection = firestore_store.examples._examples
    collection.reset_query_log()

    remaining = firestore_store.delete_example(target_pack, "Dev", 0)
    assert remaining == per_category - 1

    log = collection.query_log
    assert len(log) >= 3
    first, second, third = log[:3]

    assert ("word_pack_id", "==", target_pack) in first["filters"]
    assert ("category", "==", "Dev") in first["filters"]
    assert first["size"] == per_category

    assert ("word_pack_id", "==", target_pack) in second["filters"]
    assert ("category", "==", "Dev") in second["filters"]
    assert second["size"] == per_category - 1

    assert ("word_pack_id", "==", target_pack) in third["filters"]
    assert all(f[0] != "category" for f in third["filters"])
    total_examples_in_pack = per_category * len(categories) - 1
    assert third["size"] == total_examples_in_pack


def test_list_examples_paginates_on_server_side(
    firestore_store: AppFirestoreStore,
) -> None:
    """例文一覧のページングが Firestore クエリの limit/start_after に収まることを検証する。"""

    pack_id = "paging-pack"
    total_examples = 120
    payload = {
        "lemma": "Paginate",
        "examples": {
            "Dev": [
                {"en": f"Example {idx}", "ja": f"例文 {idx}"}
                for idx in range(total_examples)
            ]
        },
    }
    firestore_store.save_word_pack(
        pack_id, payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    collection = firestore_store.examples._examples
    collection.reset_query_log()

    page = firestore_store.list_examples(limit=50, offset=50)

    assert len(page) == 50
    assert collection.query_log, "expected queries to be recorded"
    assert len(collection.query_log) == 2
    assert max(entry["size"] for entry in collection.query_log) <= 50
    assert sum(entry["size"] for entry in collection.query_log) <= 100


def test_delete_examples_uses_paged_batching(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    wordpack_store = firestore_store.wordpacks
    monkeypatch.setattr(wordpack_store, "_EXAMPLE_DELETE_BATCH_SIZE", 5)

    payload = {
        "lemma": "BulkDelete",
        "examples": {
            "Dev": [
                {"en": f"Example {idx}", "ja": f"例文 {idx}"} for idx in range(12)
            ]
        },
    }
    wordpack_store.save_word_pack(
        "bulk-pack", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    payload_other = {
        "lemma": "KeepMe",
        "examples": {"Dev": [{"en": "keep", "ja": "残す"}]},
    }
    wordpack_store.save_word_pack(
        "other-pack", payload_other["lemma"], json.dumps(payload_other, ensure_ascii=False)
    )

    collection = wordpack_store._examples
    collection.reset_query_log()

    wordpack_store._delete_examples("bulk-pack")

    log = collection.query_log
    assert len(log) == 3
    assert all(("word_pack_id", "==", "bulk-pack") in entry["filters"] for entry in log)
    assert max(entry["size"] for entry in log) <= 5

    remaining_examples = [
        snap
        for snap in collection._all_snapshots()
        if (snap.to_dict() or {}).get("word_pack_id") == "bulk-pack"
    ]
    assert not remaining_examples

    other_examples = [
        snap
        for snap in collection._all_snapshots()
        if (snap.to_dict() or {}).get("word_pack_id") == "other-pack"
    ]
    assert len(other_examples) == 1


def test_delete_word_pack_skips_scan_when_no_examples(
    firestore_store: AppFirestoreStore,
) -> None:
    pack_id = "empty-pack"
    payload = {"lemma": "Empty", "examples": {}}
    firestore_store.save_word_pack(pack_id, payload["lemma"], json.dumps(payload))

    collection = firestore_store.wordpacks._examples
    collection.reset_query_log()

    deleted = firestore_store.delete_word_pack(pack_id)

    assert deleted is True
    assert collection.query_log == []
    assert firestore_store.wordpacks.get_word_pack_metadata(pack_id) is None


def test_delete_examples_can_be_retried_after_batch_failure(
    firestore_store: AppFirestoreStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    wordpack_store = firestore_store.wordpacks
    payload = {
        "lemma": "Retryable",
        "examples": {"Dev": [{"en": "a", "ja": "b"}, {"en": "c", "ja": "d"}]},
    }
    wordpack_store.save_word_pack(
        "retry-pack", payload["lemma"], json.dumps(payload, ensure_ascii=False)
    )

    class FailingBatch(FakeWriteBatch):
        def commit(self) -> None:  # type: ignore[override]
            raise RuntimeError("boom")

    monkeypatch.setattr(wordpack_store._client, "batch", lambda: FailingBatch(wordpack_store._client))

    with pytest.raises(RuntimeError):
        wordpack_store._delete_examples("retry-pack")

    remaining_after_failure = [
        snap
        for snap in wordpack_store._examples._all_snapshots()
        if (snap.to_dict() or {}).get("word_pack_id") == "retry-pack"
    ]
    assert len(remaining_after_failure) == 2

    monkeypatch.setattr(wordpack_store._client, "batch", lambda: FakeWriteBatch(wordpack_store._client))
    wordpack_store._delete_examples("retry-pack")

    remaining_after_retry = [
        snap
        for snap in wordpack_store._examples._all_snapshots()
        if (snap.to_dict() or {}).get("word_pack_id") == "retry-pack"
    ]
    assert not remaining_after_retry
