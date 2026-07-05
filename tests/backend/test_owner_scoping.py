from __future__ import annotations

import json

import pytest

from backend.store import AppFirestoreStore
from tests.firestore_fakes import ensure_firestore_test_env, use_fake_firestore_client


@pytest.fixture()
def store(monkeypatch: pytest.MonkeyPatch) -> AppFirestoreStore:
    ensure_firestore_test_env(monkeypatch)
    return AppFirestoreStore(client=use_fake_firestore_client(monkeypatch))


def test_wordpack_owner_visibility_is_stored(store: AppFirestoreStore) -> None:
    store.save_word_pack(
        "wp-owner",
        "owner",
        json.dumps({"lemma": "owner", "examples": {}}),
        metadata={"owner_user_id": "user-owner"},
    )

    visibility = store.get_word_pack_visibility("wp-owner")
    assert visibility == {"guest_public": False, "owner_user_id": "user-owner"}


def test_owned_wordpack_list_filters_by_owner(store: AppFirestoreStore) -> None:
    store.save_word_pack(
        "wp-owner-a",
        "owner-a",
        json.dumps({"lemma": "owner-a", "examples": {}}),
        metadata={"owner_user_id": "user-a"},
    )
    store.save_word_pack(
        "wp-owner-b",
        "owner-b",
        json.dumps({"lemma": "owner-b", "examples": {}}),
        metadata={"owner_user_id": "user-b"},
    )

    rows = store.list_owned_word_packs_with_flags("user-a")

    assert [row[0] for row in rows] == ["wp-owner-a"]
    assert store.count_owned_word_packs("user-a") == 1


def test_article_owner_visibility_is_stored(store: AppFirestoreStore) -> None:
    store.save_article(
        "art-owner",
        title_en="Owned",
        body_en="Owned body",
        body_ja="所有された本文",
        notes_ja=None,
        owner_user_id="user-owner",
    )

    visibility = store.get_article_visibility("art-owner")
    assert visibility == {"guest_public": False, "owner_user_id": "user-owner"}


def test_owned_article_list_filters_by_owner(store: AppFirestoreStore) -> None:
    store.save_article(
        "art-owner-a",
        title_en="Owned A",
        body_en="Body A",
        body_ja="本文A",
        notes_ja=None,
        owner_user_id="user-a",
    )
    store.save_article(
        "art-owner-b",
        title_en="Owned B",
        body_en="Body B",
        body_ja="本文B",
        notes_ja=None,
        owner_user_id="user-b",
    )

    rows = store.list_articles(owner_user_id="user-a")

    assert [row[0] for row in rows] == ["art-owner-a"]
    assert store.count_articles(owner_user_id="user-a") == 1


def test_quiz_owner_visibility_and_attempt_owner_are_stored(store: AppFirestoreStore) -> None:
    payload = {
        "title_en": "Owned quiz",
        "format_profile": "single_passage",
        "generation_domain": "technical",
        "domain_intensity": "standard",
        "difficulty": "medium",
        "passages": [{"id": "p1", "body_en": "Body", "body_ja": "本文"}],
        "sections": [{"id": "s1", "questions": []}],
        "related_word_packs": [],
        "owner_user_id": "user-owner",
    }
    store.save_quiz("quiz-owner", payload, [])
    store.save_quiz_attempt(
        "attempt-owner",
        {"quiz_id": "quiz-owner", "owner_user_id": "user-owner"},
    )

    visibility = store.get_quiz_visibility("quiz-owner")
    assert visibility == {"guest_public": False, "owner_user_id": "user-owner"}
    assert store._client._data["quiz_attempts"]["attempt-owner"]["owner_user_id"] == "user-owner"


def test_owned_quiz_list_filters_by_owner(store: AppFirestoreStore) -> None:
    payload = {
        "title_en": "Owned quiz",
        "format_profile": "single_passage",
        "generation_domain": "technical",
        "domain_intensity": "standard",
        "difficulty": "medium",
        "passages": [{"id": "p1", "body_en": "Body", "body_ja": "本文"}],
        "sections": [{"id": "s1", "questions": []}],
        "related_word_packs": [],
    }
    store.save_quiz("quiz-owner-a", {**payload, "owner_user_id": "user-a"}, [])
    store.save_quiz("quiz-owner-b", {**payload, "owner_user_id": "user-b"}, [])

    rows = store.list_quizzes(owner_user_id="user-a")

    assert [row["id"] for row in rows] == ["quiz-owner-a"]
    assert store.count_quizzes(owner_user_id="user-a") == 1


def test_example_parent_wordpack_id_is_available_before_study_progress_update(
    store: AppFirestoreStore,
) -> None:
    store.save_word_pack(
        "wp-example-owner",
        "example-owner",
        json.dumps({"lemma": "example-owner", "examples": {}}),
        metadata={"owner_user_id": "user-owner"},
    )
    added_count = store.append_examples(
        "wp-example-owner",
        "Dev",
        [{"en": "Hello.", "ja": "こんにちは。"}],
    )
    example_id = int(next(iter(store._client._data["examples"].keys())))

    assert added_count == 1
    assert store.get_example_word_pack_id(example_id) == "wp-example-owner"
