"""ゲストモードの判定と書き込み制限ミドルウェアの契約テスト。"""

from __future__ import annotations

import json
import os
import sys
from http import HTTPStatus
from pathlib import Path

import pytest

# Firestore エミュレータを利用して認証不要のクライアントを使う。
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8080")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test-project")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")

# apps/backend 配下のモジュールを直接インポートできるようパスを明示的に追加する。
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from fastapi.testclient import TestClient

from backend.config import settings
from backend.store import AppFirestoreStore
from tests.firestore_fakes import (
    FakeFirestoreClient,
    ensure_firestore_test_env,
    use_fake_firestore_client,
)


@pytest.fixture()
def guest_test_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, AppFirestoreStore]:
    """ゲストモード関連の API を検証するための TestClient を構築する。"""

    ensure_firestore_test_env(monkeypatch)
    store_instance = AppFirestoreStore(client=use_fake_firestore_client(monkeypatch))
    assert isinstance(store_instance._client, FakeFirestoreClient)

    import backend.store as store_module
    import backend.auth as auth_module
    import backend.routers.word as word_router_module
    import backend.routers.article as article_router_module

    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "firestore_emulator_host", "localhost:8080")
    monkeypatch.setattr(settings, "firestore_project_id", "test-project")
    monkeypatch.setattr(settings, "gcp_project_id", "test-project")
    monkeypatch.setattr(settings, "session_secret_key", "guest-secret-key")
    monkeypatch.setattr(settings, "session_max_age_seconds", 3600)
    monkeypatch.setattr(settings, "guest_session_cookie_name", "wp_guest")
    monkeypatch.setattr(settings, "guest_session_max_age_seconds", 1800)
    monkeypatch.setattr(settings, "strict_mode", False)
    monkeypatch.setattr(settings, "disable_session_auth", False)
    monkeypatch.setattr(store_module, "AppFirestoreStore", lambda *args, **kwargs: store_instance)
    monkeypatch.setattr(store_module, "store", store_instance)
    monkeypatch.setattr(auth_module, "store", store_instance)
    monkeypatch.setattr(word_router_module, "store", store_instance)
    monkeypatch.setattr(article_router_module, "store", store_instance)

    from backend.main import create_app

    app = create_app()
    return TestClient(app), store_instance


def _seed_wordpack(store: AppFirestoreStore, lemma: str) -> None:
    """ゲスト閲覧の対象になる WordPack データを最小構成で保存する。"""

    payload = {
        "lemma": lemma,
        "sense_title": f"{lemma} title",
        "examples": {},
    }
    store.save_word_pack(f"wp-{lemma}", lemma, json.dumps(payload, ensure_ascii=False))


def _seed_public_wordpack(store: AppFirestoreStore, lemma: str) -> None:
    """ゲスト公開フラグ付きの WordPack を保存する。"""

    payload = {
        "lemma": lemma,
        "sense_title": f"{lemma} title",
        "examples": {},
    }
    store.save_word_pack(
        f"wp-{lemma}",
        lemma,
        json.dumps(payload, ensure_ascii=False),
        metadata={"guest_public": True},
    )


def _seed_wordpack_with_example(
    store: AppFirestoreStore, lemma: str, *, guest_public: bool
) -> None:
    """例文一覧のゲスト公開フィルタを検証するための WordPack を保存する。"""

    payload = {
        "lemma": lemma,
        "sense_title": f"{lemma} title",
        "examples": {
            "Common": [
                {
                    "en": f"{lemma} appears in context.",
                    "ja": f"{lemma} が文脈に出てきます。",
                }
            ]
        },
    }
    metadata = {"guest_public": True} if guest_public else None
    store.save_word_pack(
        f"wp-{lemma}",
        lemma,
        json.dumps(payload, ensure_ascii=False),
        metadata=metadata,
    )


def _seed_article(
    store: AppFirestoreStore,
    article_id: str,
    *,
    title: str,
    guest_public: bool,
    links: list[tuple[str, str, str]] | None = None,
) -> None:
    store.save_article(
        article_id,
        title_en=title,
        body_en=f"{title} body",
        body_ja=f"{title} の本文",
        notes_ja=None,
        related_word_packs=links or [],
        guest_public=guest_public,
    )


def _seed_quiz(
    store: AppFirestoreStore,
    quiz_id: str,
    *,
    title: str,
    guest_public: bool,
) -> None:
    payload = {
        "id": quiz_id,
        "title_en": title,
        "format_profile": "single_passage",
        "generation_domain": "technical",
        "domain_intensity": "standard",
        "difficulty": "medium",
        "passages": [
            {
                "id": "p1",
                "order": 1,
                "kind": "article",
                "title": "Guest reading",
                "body_en": "Guests can read public content.",
                "body_ja": "ゲストは公開コンテンツを読めます。",
                "speaker_labels": [],
            }
        ],
        "notes_ja": None,
        "sections": [
            {
                "id": "s1",
                "order": 1,
                "title": "Reading",
                "description_ja": None,
                "passage_ids": ["p1"],
                "questions": [
                    {
                        "id": "q1",
                        "order": 1,
                        "type": "detail",
                        "prompt": "What can guests read?",
                        "choices": [
                            {"id": "A", "text": "Public content"},
                            {"id": "B", "text": "Private drafts"},
                            {"id": "C", "text": "Deleted content"},
                            {"id": "D", "text": "Credentials"},
                        ],
                        "correct_choice_id": "A",
                        "explanation": {
                            "explanation_ja": "本文に public content とあります。",
                            "evidence_passage_id": "p1",
                            "evidence_text": "public content",
                            "evidence_start": 16,
                            "evidence_end": 30,
                            "wrong_choice_explanations_ja": {},
                            "related_lemmas": [],
                        },
                    }
                ],
            }
        ],
        "related_word_packs": [],
        "source_word_pack_ids": [],
        "source_lemmas": ["public"],
        "topic_seed": None,
        "avoid_topics": [],
        "guest_public": guest_public,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-02T00:00:00+00:00",
    }
    store.save_quiz(quiz_id, payload, payload["related_word_packs"])


def test_guest_session_cookie_is_issued(guest_test_client: tuple[TestClient, AppFirestoreStore]) -> None:
    """ゲストセッション発行エンドポイントが署名済み Cookie を返すことを確認する。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"mode": "guest"}

    cookie_name = settings.guest_session_cookie_name
    assert client.cookies.get(cookie_name)
    assert client.cookies.get("__session") == client.cookies.get(cookie_name)


def test_guest_logout_deletes_guest_session_cookie(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲスト閲覧モードからのログアウトでゲスト Cookie を失効させる。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK
    cookie_name = settings.guest_session_cookie_name
    assert client.cookies.get(cookie_name)

    logout = client.post("/api/auth/logout")
    assert logout.status_code == HTTPStatus.NO_CONTENT
    assert client.cookies.get(cookie_name) is None
    assert client.cookies.get("__session") is None
    assert f"{cookie_name}=" in (logout.headers.get("set-cookie") or "")


def test_guest_logout_deletes_firebase_cookie_alias(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """Firebase Hosting 経由で __session だけ届くゲストもログアウトできる。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK
    cookie_name = settings.guest_session_cookie_name
    del client.cookies[cookie_name]
    assert client.cookies.get("__session")

    logout = client.post("/api/auth/logout")
    assert logout.status_code == HTTPStatus.NO_CONTENT
    assert client.cookies.get("__session") is None


def test_guest_can_access_readonly_endpoint(guest_test_client: tuple[TestClient, AppFirestoreStore]) -> None:
    """ゲストセッションで WordPack の閲覧系 API が利用できることを確認する。"""

    client, store = guest_test_client
    _seed_public_wordpack(store, "guest")

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    lookup = client.get("/api/word/", params={"lemma": "guest"})
    assert lookup.status_code == HTTPStatus.OK
    assert lookup.json()["lemma"] == "guest"


def test_guest_can_access_readonly_endpoint_with_firebase_cookie_alias(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """Firebase Hosting 経由で __session だけ届いてもゲスト閲覧できる。"""

    client, store = guest_test_client
    _seed_public_wordpack(store, "guest-alias")

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    cookie_name = settings.guest_session_cookie_name
    assert client.cookies.get("__session")
    del client.cookies[cookie_name]

    lookup = client.get("/api/word/", params={"lemma": "guest-alias"})
    assert lookup.status_code == HTTPStatus.OK
    assert lookup.json()["lemma"] == "guest-alias"


def test_invalid_firebase_session_alias_is_not_treated_as_guest(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """壊れた通常セッションを __session 経由のゲストとして誤認しない。"""

    client, store = guest_test_client
    _seed_public_wordpack(store, "guest-invalid")
    client.cookies.set("__session", "not-a-signed-session")

    lookup = client.get("/api/word/", params={"lemma": "guest-invalid"})
    assert lookup.status_code == HTTPStatus.UNAUTHORIZED
    assert lookup.json()["detail"] == "Invalid session token"


def test_guest_write_is_denied(guest_test_client: tuple[TestClient, AppFirestoreStore]) -> None:
    """ゲストセッションは書き込み系の API を 403 で拒否される。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK
    # なぜ: セッション Cookie が無い状態でもゲスト Cookie による拒否が有効かを明示する。
    assert client.cookies.get(settings.session_cookie_name) is None

    denied = client.post("/api/word/packs", json={"lemma": "blocked"})
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["detail"] == "Guest mode cannot perform write operations"


def test_guest_write_is_denied_with_firebase_cookie_alias(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """__session にミラーされたゲスト Cookie だけでも書き込みを拒否する。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    cookie_name = settings.guest_session_cookie_name
    del client.cookies[cookie_name]

    denied = client.post("/api/word/packs", json={"lemma": "blocked-alias"})
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["detail"] == "Guest mode cannot perform write operations"


def test_guest_lookup_missing_word_is_rejected(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲストで未登録語を要求しても生成されず拒否されることを確認する。"""

    client, store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    lookup = client.get("/api/word/", params={"lemma": "unknown"})
    assert lookup.status_code == HTTPStatus.FORBIDDEN
    assert lookup.json()["detail"] == "Guest mode cannot generate WordPack"
    assert store.find_word_pack_by_lemma_ci("unknown") is None


def test_guest_list_filters_private_wordpacks(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲスト閲覧では guest_public=true の WordPack のみ一覧に表示される。"""

    client, store = guest_test_client
    _seed_public_wordpack(store, "public")
    _seed_wordpack(store, "private")

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    listing = client.get("/api/word/packs?limit=50&offset=0")
    assert listing.status_code == HTTPStatus.OK
    payload = listing.json()
    lemmas = [item["lemma"] for item in payload.get("items", [])]
    assert "public" in lemmas
    assert "private" not in lemmas


def test_guest_example_list_filters_private_wordpack_examples(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲスト閲覧の例文一覧は公開 WordPack に紐づく例文だけを返す。"""

    client, store = guest_test_client
    _seed_wordpack_with_example(store, "public-example", guest_public=True)
    _seed_wordpack_with_example(store, "private-example", guest_public=False)

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    listing = client.get("/api/word/examples?limit=50&offset=0")

    assert listing.status_code == HTTPStatus.OK
    payload = listing.json()
    lemmas = [item["lemma"] for item in payload.get("items", [])]
    assert lemmas == ["public-example"]
    assert payload["total"] == 1


def test_guest_article_list_and_detail_filter_private_content(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲスト閲覧の Reader は公開記事だけを返し、非公開 WordPack link を隠す。"""

    client, store = guest_test_client
    _seed_public_wordpack(store, "public-link")
    _seed_wordpack(store, "private-link")
    _seed_article(
        store,
        "article-public",
        title="Public Article",
        guest_public=True,
        links=[
            ("wp-public-link", "public-link", "existing"),
            ("wp-private-link", "private-link", "existing"),
        ],
    )
    _seed_article(store, "article-private", title="Private Article", guest_public=False)

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    listing = client.get("/api/article?limit=50&offset=0")
    assert listing.status_code == HTTPStatus.OK
    payload = listing.json()
    assert [item["id"] for item in payload["items"]] == ["article-public"]
    assert payload["items"][0]["guest_public"] is True
    assert payload["total"] == 1

    detail = client.get("/api/article/article-public")
    assert detail.status_code == HTTPStatus.OK
    links = detail.json()["related_word_packs"]
    assert [link["word_pack_id"] for link in links] == ["wp-public-link"]

    hidden = client.get("/api/article/article-private")
    assert hidden.status_code == HTTPStatus.NOT_FOUND


def test_guest_quiz_list_and_detail_filter_private_content(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲスト閲覧の Quiz は guest_public=true の Quiz だけを返す。"""

    client, store = guest_test_client
    _seed_quiz(store, "quiz-public", title="Public Quiz", guest_public=True)
    _seed_quiz(store, "quiz-private", title="Private Quiz", guest_public=False)

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    listing = client.get("/api/quiz?limit=50&offset=0")
    assert listing.status_code == HTTPStatus.OK
    payload = listing.json()
    assert [item["id"] for item in payload["items"]] == ["quiz-public"]
    assert payload["items"][0]["guest_public"] is True
    assert payload["total"] == 1

    public_detail = client.get("/api/quiz/quiz-public")
    assert public_detail.status_code == HTTPStatus.OK

    hidden = client.get("/api/quiz/quiz-private")
    assert hidden.status_code == HTTPStatus.NOT_FOUND


def test_guest_delete_is_denied(guest_test_client: tuple[TestClient, AppFirestoreStore]) -> None:
    """ゲストセッションが DELETE 要求を拒否することを確認する。"""

    client, _store = guest_test_client

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    denied = client.delete("/api/word/packs/wp-guest")
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["detail"] == "Guest mode cannot perform write operations"


def test_guest_public_update_is_denied(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """ゲストセッションは公開フラグ更新APIも拒否される。"""

    client, store = guest_test_client
    _seed_wordpack(store, "blocked")
    _seed_article(store, "article-blocked", title="Blocked Article", guest_public=False)
    _seed_quiz(store, "quiz-blocked", title="Blocked Quiz", guest_public=False)

    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    denied = client.post("/api/word/packs/wp-blocked/guest-public", json={"guest_public": True})
    assert denied.status_code == HTTPStatus.FORBIDDEN
    assert denied.json()["detail"] == "Guest mode cannot perform write operations"

    article_denied = client.post(
        "/api/article/article-blocked/guest-public",
        json={"guest_public": True},
    )
    assert article_denied.status_code == HTTPStatus.FORBIDDEN
    assert article_denied.json()["detail"] == "Guest mode cannot perform write operations"

    quiz_denied = client.post(
        "/api/quiz/quiz-blocked/guest-public",
        json={"guest_public": True},
    )
    assert quiz_denied.status_code == HTTPStatus.FORBIDDEN
    assert quiz_denied.json()["detail"] == "Guest mode cannot perform write operations"


def test_authenticated_user_not_treated_as_guest_when_cookie_lingers(
    guest_test_client: tuple[TestClient, AppFirestoreStore],
) -> None:
    """認証済みユーザーがゲスト Cookie を持っていてもゲスト扱いされないことを確認する。
    
    シナリオ: ユーザーがゲストとして開始し、その後ログインした場合、
    ゲスト Cookie が残存していても認証済みとして扱われる。
    未登録語を要求した場合、403 (ゲスト拒否) ではなく 404 (未登録) を返すべき。
    
    なぜ: Firebase Hosting 経由では __session が user/guest どちらの alias にもなるため、
          ログイン後に wp_guest が残っても user の __session が優先される必要がある。
    """
    client, store = guest_test_client

    guest_response = client.post("/api/auth/guest")
    assert guest_response.status_code == HTTPStatus.OK
    guest_cookie_name = settings.guest_session_cookie_name
    assert client.cookies.get(guest_cookie_name)

    user_id = "sub-cookie-lingers"
    store.record_user_login(
        google_sub=user_id,
        email="linger@example.com",
        display_name="Lingering Guest Cookie",
    )

    import backend.auth as auth_module

    user_token = auth_module.issue_session_token(user_id)
    client.cookies.set(settings.session_cookie_name or "wp_session", user_token)
    client.cookies.set("__session", user_token)
    assert client.cookies.get(guest_cookie_name)

    lookup = client.get("/api/word/", params={"lemma": "missing-authenticated"})
    assert lookup.status_code == HTTPStatus.NOT_FOUND
    assert lookup.json()["detail"] == "WordPack not found"
