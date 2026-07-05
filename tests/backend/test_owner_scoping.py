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
