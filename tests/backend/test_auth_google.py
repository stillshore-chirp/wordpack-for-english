from __future__ import annotations

import json
import hashlib
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.config import settings
from backend.main import create_app
from backend.store import AppFirestoreStore
from tests.firestore_fakes import FakeFirestoreClient, ensure_firestore_test_env, use_fake_firestore_client


@pytest.fixture()
def test_client(monkeypatch) -> TestClient:
    """Create an isolated FastAPI test client with a dedicated Firestore store."""

    ensure_firestore_test_env(monkeypatch)
    store_instance = AppFirestoreStore(client=use_fake_firestore_client(monkeypatch))
    assert isinstance(store_instance._client, FakeFirestoreClient)

    import backend.store as store_module
    import backend.auth as auth_module
    import backend.routers.auth as auth_router_module
    import backend.routers.word as word_router_module
    import backend.routers.article as article_router_module
    monkeypatch.setattr(store_module, "store", store_instance)
    monkeypatch.setattr(auth_module, "store", store_instance)
    monkeypatch.setattr(auth_router_module, "store", store_instance)
    monkeypatch.setattr(word_router_module, "store", store_instance)
    monkeypatch.setattr(article_router_module, "store", store_instance)
    monkeypatch.setattr(store_module, "AppFirestoreStore", lambda *args, **kwargs: store_instance)

    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "firestore_emulator_host", "localhost:8080")
    monkeypatch.setattr(settings, "firestore_project_id", "test-project")
    monkeypatch.setattr(settings, "gcp_project_id", "test-project")
    monkeypatch.setattr(settings, "google_client_id", "test-client-id")
    monkeypatch.setattr(settings, "google_allowed_hd", "example.com")
    monkeypatch.setattr(settings, "session_secret_key", "super-secret-key")
    monkeypatch.setattr(settings, "session_max_age_seconds", 3600)
    monkeypatch.setattr(settings, "strict_mode", False)
    monkeypatch.setattr(settings, "disable_session_auth", False)
    monkeypatch.setattr(
        settings,
        "admin_email_allowlist",
        ("user@example.com", "document@example.com", "skew@example.com"),
    )

    # Recreate the app after patching shared modules to ensure new dependencies are wired.
    app = create_app()
    return TestClient(app)


def _stub_verifier(monkeypatch: pytest.MonkeyPatch, factory: Callable[[], dict[str, str]]) -> None:
    import backend.routers.auth as auth_router_module

    def _verify(token: str, audience: str, clock_skew_seconds: int) -> dict[str, str]:
        assert audience == settings.google_client_id
        return factory()

    monkeypatch.setattr(auth_router_module, "_verify_google_id_token", _verify)


def _structlog_events(caplog: pytest.LogCaptureFixture, event: str) -> list[dict[str, Any]]:
    """Collect structlog JSON payloads matching the specified event name."""

    matches: list[dict[str, Any]] = []
    for record in caplog.records:
        raw = record.getMessage()
        try:
            if isinstance(raw, str):
                payload = json.loads(raw)
            elif isinstance(raw, dict):
                payload = raw
            else:
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        if payload.get("event") == event:
            matches.append(payload)
    return matches


def test_google_auth_success_flow(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful Google sign-in returns cookie and allows protected access."""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-123",
            "email": "user@example.com",
            "name": "Example User",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    with caplog.at_level("INFO"):
        login_response = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == 200
    body = login_response.json()
    assert body["user"]["google_sub"] == "sub-123"
    assert "last_login_at" in body["user"]

    cookie = SimpleCookie()
    cookie.load(login_response.headers["set-cookie"])
    assert settings.session_cookie_name in cookie

    protected = test_client.get("/api/word/")
    assert protected.status_code in {200, 422, 501}
    # 422 はクエリ必須パラメータが欠けているだけで、認証は通っていることを示す。
    assert protected.status_code != 401

    log_entries = _structlog_events(caplog, "google_auth_succeeded")
    assert log_entries, "expected google_auth_succeeded log entry"
    latest = log_entries[-1]
    assert latest["reason"] == "authenticated"
    expected_hash = hashlib.sha256("user@example.com".lower().encode("utf-8")).hexdigest()[:12]
    assert latest["email_hash"] == expected_hash
    assert "email" not in latest
    expected_user_hash = hashlib.sha256("sub-123".lower().encode("utf-8")).hexdigest()[:12]
    assert latest["user_id_hash"] == expected_user_hash
    assert "user_id" not in latest
    expected_display_hash = hashlib.sha256("Example User".lower().encode("utf-8")).hexdigest()[:12]
    assert latest["display_name_hash"] == expected_display_hash
    assert "display_name" not in latest


def test_google_auth_sets_firebase_session_cookie_alias(
    test_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """セッション Cookie を __session にもミラーし、Firebase Hosting 経由でも認証できる。"""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-alias",
            "email": "user@example.com",
            "name": "Alias User",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    login_response = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == 200

    primary_name = settings.session_cookie_name or "wp_session"
    primary_cookie = test_client.cookies.get(primary_name)
    alias_cookie = test_client.cookies.get("__session")

    assert primary_cookie, "primary session cookie must be issued"
    assert alias_cookie, "__session cookie must mirror the session token"

    # Firebase Hosting は __session 以外の Cookie をバックエンドへ転送しないため、
    # wp_session が欠落しても __session のみでアクセスできることを検証する。
    if primary_name in test_client.cookies:
        del test_client.cookies[primary_name]

    protected = test_client.get("/api/word/")
    assert protected.status_code in {200, 422, 501}
    assert protected.status_code != 401


def test_google_auth_rejects_wrong_domain(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Hosted domain mismatch should result in HTTP 403."""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-456",
            "email": "user@other.com",
            "name": "Other Domain",
            "hd": "other.com",
            "email_verified": True,
        },
    )

    with caplog.at_level("WARNING"):
        resp = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert resp.status_code == 403

    log_entries = _structlog_events(caplog, "google_auth_denied")
    assert log_entries, "expected google_auth_denied log entry"
    log = log_entries[-1]
    assert log["reason"] == "domain_mismatch"
    assert log["hosted_domain"] == "other.com"
    assert log["allowed_domain"] == "example.com"
    expected_hash = hashlib.sha256("user@other.com".lower().encode("utf-8")).hexdigest()[:12]
    assert log["email_hash"] == expected_hash


def test_google_auth_rejects_email_not_allowlisted(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Emails outside ADMIN_EMAIL_ALLOWLIST must be denied even if the domain matches."""

    monkeypatch.setattr(settings, "admin_email_allowlist", ("admin@example.com",))

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-allowlist-deny",
            "email": "user@example.com",
            "name": "Outside Allowlist",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    with caplog.at_level("WARNING"):
        resp = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Google account email is not allowlisted"

    log_entries = _structlog_events(caplog, "google_auth_denied")
    matching = [entry for entry in log_entries if entry.get("reason") == "email_not_allowlisted"]
    assert matching, "expected email_not_allowlisted log entry"
    latest = matching[-1]
    assert latest["allowlist_size"] == 1
    assert latest["hosted_domain"] == "example.com"
    expected_hash = hashlib.sha256("user@example.com".lower().encode("utf-8")).hexdigest()[:12]
    assert latest["email_hash"] == expected_hash


def test_google_auth_rejects_unverified_email(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """ID token が未検証メールを示した場合は 403 と構造化ログを返す。"""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-unverified",
            "email": "pending@example.com",
            "name": "Pending User",
            "hd": "example.com",
            "email_verified": False,
        },
    )

    with caplog.at_level("WARNING"):
        resp = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Google account email must be verified"

    log_entries = _structlog_events(caplog, "google_auth_denied")
    matching = [entry for entry in log_entries if entry.get("reason") == "email_unverified"]
    assert matching, "expected email_unverified log entry"
    log = matching[-1]
    expected_hash = hashlib.sha256("pending@example.com".lower().encode("utf-8")).hexdigest()[:12]
    assert log["email_hash"] == expected_hash
    expected_user_hash = hashlib.sha256("sub-unverified".lower().encode("utf-8")).hexdigest()[:12]
    assert log["user_id_hash"] == expected_user_hash
    assert "user_id" not in log


def test_google_auth_invalid_signature(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Invalid token signature should produce HTTP 401."""

    import backend.routers.auth as auth_router_module

    def _raise(token: str, audience: str, clock_skew_seconds: int) -> dict[str, str]:
        raise ValueError("bad signature")

    monkeypatch.setattr(auth_router_module, "_verify_google_id_token", _raise)

    with caplog.at_level("WARNING"):
        resp = test_client.post("/api/auth/google", json={"id_token": "invalid"})
    assert resp.status_code == 401

    log_entries = _structlog_events(caplog, "google_auth_failed")
    assert log_entries, "expected google_auth_failed log entry"
    log = log_entries[-1]
    assert log["reason"] == "invalid_token"
    assert "bad signature" in log["error"]


def test_google_auth_missing_claims_logs_details(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Ensure missing claims branch records claim names and hashed email."""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-789",
            "email": "",
            "name": None,
            "hd": "example.com",
            "email_verified": True,
        },
    )

    with caplog.at_level("WARNING"):
        resp = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert resp.status_code == 401

    log_entries = _structlog_events(caplog, "google_auth_failed")
    filtered = [entry for entry in log_entries if entry.get("reason") == "missing_claims"]
    assert filtered, "expected missing_claims log entry"
    log = filtered[-1]
    assert log["missing_claims"] == ["email"]
    assert log.get("email_hash") is None


def test_protected_endpoint_requires_cookie(test_client: TestClient) -> None:
    """Requests without a valid session cookie must fail with 401."""

    # Ensure cookie jar is cleared before hitting protected endpoint
    test_client.cookies.clear()
    resp = test_client.get("/api/word/")
    assert resp.status_code == 401


def test_http_session_cookie_visible_for_document_cookie(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """HTTP ローカル環境でも document.cookie からセッションクッキーを参照できることを保証する。"""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-http",
            "email": "document@example.com",
            "name": "Doc Cookie",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    login_response = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == 200

    set_cookie_header = login_response.headers["set-cookie"]
    assert "Secure" not in set_cookie_header

    # document.cookie で参照できる前提条件: CookieJar へ平文HTTPでも保存されていること
    session_cookie_value = test_client.cookies.get(settings.session_cookie_name)
    assert session_cookie_value


def test_guest_public_update_requires_authenticated_user(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """許可されたログインユーザーのみゲスト公開フラグを更新できる。"""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-guest-public",
            "email": "user@example.com",
            "name": "Allowed User",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    login_response = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == 200

    from backend.store import store as backend_store

    payload = {"lemma": "publicized", "sense_title": "public", "examples": {}}
    backend_store.save_word_pack("wp-publicized", "publicized", json.dumps(payload, ensure_ascii=False))

    resp = test_client.post(
        "/api/word/packs/wp-publicized/guest-public",
        json={"guest_public": True},
    )
    assert resp.status_code == 200
    assert resp.json() == {"word_pack_id": "wp-publicized", "guest_public": True}

    metadata = backend_store.wordpacks.get_word_pack_metadata("wp-publicized") or {}
    assert metadata.get("metadata", {}).get("guest_public") is True


def test_guest_public_pack_is_visible_in_guest_list(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """公開フラグ更新後にゲスト一覧へ表示されることを確認する。"""

    _stub_verifier(
        monkeypatch,
        lambda: {
            "sub": "sub-guest-list",
            "email": "user@example.com",
            "name": "Allowed User",
            "hd": "example.com",
            "email_verified": True,
        },
    )

    login_response = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert login_response.status_code == 200

    from backend.store import store as backend_store

    payload = {"lemma": "exposed", "sense_title": "exposed", "examples": {}}
    backend_store.save_word_pack("wp-exposed", "exposed", json.dumps(payload, ensure_ascii=False))

    update_resp = test_client.post(
        "/api/word/packs/wp-exposed/guest-public",
        json={"guest_public": True},
    )
    assert update_resp.status_code == 200

    test_client.cookies.clear()
    guest_response = test_client.post("/api/auth/guest")
    assert guest_response.status_code == 200

    listing = test_client.get("/api/word/packs?limit=50&offset=0")
    assert listing.status_code == 200
    items = listing.json().get("items", [])
    lemmas = [item.get("lemma") for item in items]
    assert "exposed" in lemmas


def test_google_auth_passes_clock_skew_to_verifier(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """設定した clock skew 秒数が verifier に渡されることを検証する。"""

    # 設定を上書き
    monkeypatch.setattr(settings, "google_clock_skew_seconds", 120)

    import backend.routers.auth as auth_router_module

    captured: dict[str, int] = {}

    def _verify(token: str, audience: str, clock_skew_seconds: int) -> dict[str, str]:
        captured["clock_skew_in_seconds"] = clock_skew_seconds
        return {
            "sub": "sub-skew",
            "email": "skew@example.com",
            "name": "Skew OK",
            "hd": "example.com",
            "email_verified": True,
        }

    monkeypatch.setattr(auth_router_module, "_verify_google_id_token", _verify)

    resp = test_client.post("/api/auth/google", json={"id_token": "valid"})
    assert resp.status_code == 200
    # google-auth が古い場合は kwargs が無視される可能性があるため存在チェック込み
    assert captured.get("clock_skew_in_seconds") == 120
