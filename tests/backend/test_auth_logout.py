"""Unit tests for the logout endpoint ensuring cookie invalidation."""

from http import HTTPStatus
from http.cookies import SimpleCookie
import os
from pathlib import Path
import sys
import time

import pytest
import itsdangerous.timed

# backend.store の import 時に実 Firestore へ接続しないよう、テスト専用の接続先を
# モジュール読み込み前に固定する。実際のクライアントは各fixtureでフェイクへ差し替える。
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8080")
os.environ.setdefault("FIRESTORE_PROJECT_ID", "test-project")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

# apps/backend 配下のモジュールを直接インポートできるようパスを明示的に追加する。
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from fastapi.testclient import TestClient
from itsdangerous import BadSignature, URLSafeTimedSerializer

from backend.config import settings
from backend.main import create_app
from backend.store import AppFirestoreStore
from tests.firestore_fakes import (
    FakeFirestoreClient,
    ensure_firestore_test_env,
    use_fake_firestore_client,
)


def _stub_google_verifier(monkeypatch, payload_factory):
    """Google ID token 検証境界をテスト用に差し替える。"""

    import backend.routers.auth as auth_router_module

    def _verify(token: str, audience: str, clock_skew_seconds: int):
        assert audience == settings.google_client_id
        return payload_factory()

    monkeypatch.setattr(auth_router_module, "_verify_google_id_token", _verify)


def _parse_set_cookie_headers(response) -> SimpleCookie:
    """レスポンスに複数あるCookie削除指示を一つのjarへ読み込む。"""

    cookie = SimpleCookie()
    for header in response.headers.get_list("set-cookie"):
        cookie.load(header)
    return cookie


def _legacy_token(payload: dict[str, str], *, guest: bool = False) -> str:
    salt = "wordpack.guest_session" if guest else "wordpack.session"
    return URLSafeTimedSerializer(settings.session_secret_key, salt=salt).dumps(payload)


def _expired_legacy_token(
    payload: dict[str, str], *, guest: bool, monkeypatch: pytest.MonkeyPatch
) -> str:
    """現在時刻から離れた署名時刻を持つ旧Cookieを作る。"""

    real_time = time.time
    with monkeypatch.context() as context:
        context.setattr(itsdangerous.timed.time, "time", lambda: real_time() - 7200)
        return _legacy_token(payload, guest=guest)


@pytest.fixture()
def test_client(monkeypatch):
    """ログアウト関連の挙動を検証するための分離済み TestClient を構築する。"""

    ensure_firestore_test_env(monkeypatch)
    store_instance = AppFirestoreStore(client=use_fake_firestore_client(monkeypatch))
    assert isinstance(store_instance._client, FakeFirestoreClient)

    import backend.store as store_module
    import backend.auth as auth_module
    import backend.routers.auth as auth_router_module
    import backend.routers.word as word_router_module
    import backend.routers.article as article_router_module

    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "firestore_emulator_host", "localhost:8080")
    monkeypatch.setattr(settings, "firestore_project_id", "test-project")
    monkeypatch.setattr(settings, "gcp_project_id", "test-project")
    monkeypatch.setattr(store_module, "AppFirestoreStore", lambda *args, **kwargs: store_instance)
    monkeypatch.setattr(store_module, "store", store_instance)
    monkeypatch.setattr(auth_module, "store", store_instance)
    monkeypatch.setattr(auth_router_module, "store", store_instance)
    monkeypatch.setattr(word_router_module, "store", store_instance)
    monkeypatch.setattr(article_router_module, "store", store_instance)

    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_allowed_hd", "example.com")
    monkeypatch.setattr(settings, "session_secret_key", "super-secret-key")
    monkeypatch.setattr(settings, "session_max_age_seconds", 3600)
    monkeypatch.setattr(settings, "strict_mode", False)
    monkeypatch.setattr(settings, "disable_session_auth", False)
    monkeypatch.setattr(
        settings,
        "admin_email_allowlist",
        ("logout@example.com",),
    )

    app = create_app()
    return TestClient(app), store_instance


def test_logout_deletes_session_cookie(test_client, monkeypatch):
    """ログアウト時にサーバがセッション Cookie を失効させることを検証する。"""

    client, store_instance = test_client

    _stub_google_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-logout",
            "email": "logout@example.com",
            "name": "Logout Tester",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    login_response = client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == HTTPStatus.OK
    primary_cookie_name = settings.session_cookie_name or "wp_session"
    session_token = client.cookies.get(primary_cookie_name)
    assert session_token
    assert client.cookies.get("__session") == session_token

    import backend.auth as auth_module

    session_id = auth_module.verify_session_token(session_token)["sid"]

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT

    cookies = _parse_set_cookie_headers(logout_response)
    assert cookies, "logout should instruct the browser to clear the cookies"
    for cookie_name in auth_module.session_cookie_names() + auth_module.guest_session_cookie_names():
        morsel = cookies[cookie_name]
        assert morsel.value == ""
        assert morsel["max-age"] == "0"
        assert str(morsel["httponly"]).lower() == "true"

    # Requests の CookieJar も削除指示を反映していることを確認する。
    assert client.cookies.get(primary_cookie_name) is None
    assert client.cookies.get("__session") is None
    record = store_instance.get_session(session_id)
    assert record is not None
    assert record["revoked_at"]

    # 保存済みCookieを再注入しても、server-side revoke済みsessionは再利用できない。
    client.cookies.set(primary_cookie_name, session_token)
    protected_response = client.get("/api/word/")
    assert protected_response.status_code == HTTPStatus.UNAUTHORIZED
    with pytest.raises(BadSignature):
        auth_module.verify_session_token(session_token)


def test_guest_logout_revokes_server_session_and_all_cookie_aliases(test_client):
    """guest sessionもserver-side revokeされ、通常/guestの全Cookie名が削除される。"""

    client, store_instance = test_client
    response = client.post("/api/auth/guest")
    assert response.status_code == HTTPStatus.OK

    import backend.auth as auth_module

    guest_cookie_name = settings.guest_session_cookie_name or "wp_guest"
    guest_token = client.cookies.get(guest_cookie_name)
    assert guest_token
    assert client.cookies.get("__session") == guest_token
    session_id = auth_module.verify_guest_session_token(guest_token)["sid"]

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT
    cookies = _parse_set_cookie_headers(logout_response)
    for cookie_name in auth_module.session_cookie_names() + auth_module.guest_session_cookie_names():
        assert cookies[cookie_name].value == ""
        assert cookies[cookie_name]["max-age"] == "0"
        assert str(cookies[cookie_name]["httponly"]).lower() == "true"
    assert client.cookies.get(guest_cookie_name) is None
    assert client.cookies.get("__session") is None

    record = store_instance.get_session(session_id)
    assert record is not None
    assert record["revoked_at"]

    # HttpOnly Cookieを再注入しても、guest用の保護APIは401になる。
    client.cookies.set(guest_cookie_name, guest_token)
    protected_response = client.get("/api/word/packs")
    assert protected_response.status_code == HTTPStatus.UNAUTHORIZED
    with pytest.raises(BadSignature):
        auth_module.verify_guest_session_token(guest_token)


def test_logout_revokes_user_and_guest_sessions_when_all_cookie_names_are_present(
    test_client, monkeypatch
):
    """通常/guest Cookieが同時に残る状態でも全sessionを失効させる。"""

    client, store_instance = test_client
    _stub_google_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-mixed-logout",
            "email": "logout@example.com",
            "name": "Mixed Logout Tester",
            "hd": "example.com",
            "email_verified": True,
        },
    )
    login_response = client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == HTTPStatus.OK

    import backend.auth as auth_module

    user_cookie_name = settings.session_cookie_name or "wp_session"
    user_token = client.cookies.get(user_cookie_name)
    assert user_token
    user_session_id = auth_module.verify_session_token(user_token)["sid"]

    guest_response = client.post("/api/auth/guest")
    assert guest_response.status_code == HTTPStatus.OK
    guest_cookie_name = settings.guest_session_cookie_name or "wp_guest"
    guest_token = client.cookies.get(guest_cookie_name)
    assert guest_token
    guest_session_id = auth_module.verify_guest_session_token(guest_token)["sid"]
    # __session は最後に発行されたguest tokenへ更新され、通常tokenはprimary名で残る。
    assert client.cookies.get("__session") == guest_token

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT
    assert client.cookies.get(user_cookie_name) is None
    assert client.cookies.get(guest_cookie_name) is None
    assert client.cookies.get("__session") is None

    user_record = store_instance.get_session(user_session_id)
    guest_record = store_instance.get_session(guest_session_id)
    assert user_record is not None and user_record["revoked_at"]
    assert guest_record is not None and guest_record["revoked_at"]

    # 両方を個別に再注入しても認証境界を越えられないことを確認する。
    client.cookies.set(user_cookie_name, user_token)
    assert client.get("/api/word/").status_code == HTTPStatus.UNAUTHORIZED
    client.cookies.clear()
    client.cookies.set(guest_cookie_name, guest_token)
    assert client.get("/api/word/packs").status_code == HTTPStatus.UNAUTHORIZED


def test_legacy_user_cookie_cannot_be_replayed_after_logout_attempt(test_client):
    """server recordを持たない旧user Cookieはlogout後に認証へ再利用できない。"""

    client, store_instance = test_client
    user_id = "legacy-user-logout"
    store_instance.record_user_login(
        google_sub=user_id,
        email="legacy@example.com",
        display_name="Legacy User",
    )
    token = _legacy_token({"sub": user_id})
    cookie_name = settings.session_cookie_name or "wp_session"
    client.cookies.set(cookie_name, token)

    # 実装は旧Cookieを明示的に拒否するか、削除応答を返してもよいが、いずれも
    # server-side sessionが存在しない旧tokenを成功済み認証として残してはならない。
    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT

    client.cookies.clear()
    client.cookies.set(cookie_name, token)
    replay_response = client.get("/api/word/packs")
    assert replay_response.status_code == HTTPStatus.UNAUTHORIZED


def test_legacy_guest_cookie_cannot_be_replayed_after_logout_attempt(test_client):
    """server recordを持たない旧guest Cookieもlogout後に閲覧へ再利用できない。"""

    client, _store_instance = test_client
    token = _legacy_token(
        {"mode": "guest", "gid": "legacy-guest-logout"}, guest=True
    )
    cookie_name = settings.guest_session_cookie_name or "wp_guest"
    client.cookies.set(cookie_name, token)

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT

    client.cookies.clear()
    client.cookies.set(cookie_name, token)
    replay_response = client.get("/api/word/packs")
    assert replay_response.status_code == HTTPStatus.UNAUTHORIZED


def test_legacy_user_primary_and_alias_tokens_are_both_revoked(test_client):
    """異なる旧user tokenがprimary/aliasに残っても両方を失効させる。"""

    client, store_instance = test_client
    user_id = "legacy-user-alias-logout"
    store_instance.record_user_login(
        google_sub=user_id,
        email="legacy-alias@example.com",
        display_name="Legacy Alias User",
    )
    primary_token = _legacy_token({"sub": user_id, "slot": "primary"})
    alias_token = _legacy_token({"sub": user_id, "slot": "alias"})
    primary_name = settings.session_cookie_name or "wp_session"
    client.cookies.set(primary_name, primary_token)
    client.cookies.set("__session", alias_token)

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT

    for cookie_name, token in ((primary_name, primary_token), ("__session", alias_token)):
        client.cookies.clear()
        client.cookies.set(cookie_name, token)
        assert client.get("/api/word/packs").status_code == HTTPStatus.UNAUTHORIZED


def test_legacy_guest_primary_and_alias_tokens_are_both_revoked(test_client):
    """異なる旧guest tokenがprimary/aliasに残っても両方を失効させる。"""

    client, _store_instance = test_client
    primary_token = _legacy_token(
        {"mode": "guest", "gid": "legacy-guest-primary", "slot": "primary"},
        guest=True,
    )
    alias_token = _legacy_token(
        {"mode": "guest", "gid": "legacy-guest-alias", "slot": "alias"},
        guest=True,
    )
    primary_name = settings.guest_session_cookie_name or "wp_guest"
    client.cookies.set(primary_name, primary_token)
    client.cookies.set("__session", alias_token)

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == HTTPStatus.NO_CONTENT

    for cookie_name, token in ((primary_name, primary_token), ("__session", alias_token)):
        client.cookies.clear()
        client.cookies.set(cookie_name, token)
        assert client.get("/api/word/packs").status_code == HTTPStatus.UNAUTHORIZED


@pytest.mark.parametrize("guest", [False, True], ids=["user", "guest"])
def test_tampered_cookie_does_not_create_logout_tombstone(test_client, guest: bool):
    """署名不正Cookieのlogout試行でserver-side状態を新規作成しない。"""

    client, store_instance = test_client
    token = _legacy_token(
        {"mode": "guest", "gid": "tampered-guest"} if guest else {"sub": "tampered-user"},
        guest=guest,
    )
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    cookie_name = (
        settings.guest_session_cookie_name or "wp_guest"
        if guest
        else settings.session_cookie_name or "wp_session"
    )
    client.cookies.set(cookie_name, tampered)
    before = set(store_instance._client._data.get("sessions", {}))

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == HTTPStatus.NO_CONTENT
    assert set(store_instance._client._data.get("sessions", {})) == before


@pytest.mark.parametrize("guest", [False, True], ids=["user", "guest"])
def test_expired_cookie_does_not_create_logout_tombstone(
    test_client, guest: bool, monkeypatch: pytest.MonkeyPatch
):
    """期限切れCookieのlogout試行でserver-side状態を新規作成しない。"""

    client, store_instance = test_client
    token = _expired_legacy_token(
        {"mode": "guest", "gid": "expired-guest"} if guest else {"sub": "expired-user"},
        guest=guest,
        monkeypatch=monkeypatch,
    )
    cookie_name = (
        settings.guest_session_cookie_name or "wp_guest"
        if guest
        else settings.session_cookie_name or "wp_session"
    )
    client.cookies.set(cookie_name, token)
    before = set(store_instance._client._data.get("sessions", {}))

    logout_response = client.post("/api/auth/logout")

    assert logout_response.status_code == HTTPStatus.NO_CONTENT
    assert set(store_instance._client._data.get("sessions", {})) == before


def test_logout_requires_authentication(test_client):
    """Cookieがなくてもログアウト完了を返し、再試行を可能にする。"""

    client, _store_instance = test_client
    response = client.post("/api/auth/logout")
    assert response.status_code == HTTPStatus.NO_CONTENT


def test_logout_retry_after_cookie_deletion_is_idempotent(test_client, monkeypatch):
    """初回logout後にCookieが消えた再試行も204で完了する。"""

    client, _store_instance = test_client
    _stub_google_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-idempotent-logout",
            "email": "logout@example.com",
            "name": "Idempotent Logout Tester",
            "hd": "example.com",
            "email_verified": True,
        },
    )
    assert client.post("/api/auth/google", json={"id_token": "valid"}).status_code == HTTPStatus.OK
    first = client.post("/api/auth/logout")
    assert first.status_code == HTTPStatus.NO_CONTENT
    assert client.cookies.get(settings.session_cookie_name or "wp_session") is None
    assert client.cookies.get("__session") is None

    second = client.post("/api/auth/logout")
    assert second.status_code == HTTPStatus.NO_CONTENT
