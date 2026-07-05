from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pytest
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.config import settings
from backend.store import AppFirestoreStore
from tests.firestore_fakes import ensure_firestore_test_env, use_fake_firestore_client


@pytest.fixture()
def session_store(monkeypatch: pytest.MonkeyPatch) -> AppFirestoreStore:
    ensure_firestore_test_env(monkeypatch)
    store_instance = AppFirestoreStore(client=use_fake_firestore_client(monkeypatch))

    import backend.auth as auth_module

    monkeypatch.setattr(auth_module, "store", store_instance)
    monkeypatch.setattr(settings, "session_secret_key", "session-store-secret")
    monkeypatch.setattr(settings, "session_max_age_seconds", 3600)
    monkeypatch.setattr(settings, "guest_session_max_age_seconds", 1800)
    monkeypatch.setattr(settings, "session_idle_timeout_seconds", 3600)
    monkeypatch.setattr(settings, "guest_session_idle_timeout_seconds", 1800)
    monkeypatch.setattr(settings, "session_last_seen_update_interval_seconds", 0)
    return store_instance


def _decode_user_cookie(token: str) -> dict:
    serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="wordpack.session")
    return serializer.loads(token, max_age=3600)


def _decode_guest_cookie(token: str) -> dict:
    serializer = URLSafeTimedSerializer(settings.session_secret_key, salt="wordpack.guest_session")
    return serializer.loads(token, max_age=1800)


def test_user_session_cookie_contains_only_opaque_sid(session_store: AppFirestoreStore) -> None:
    import backend.auth as auth_module

    token = auth_module.issue_session_token("google-sub-1")
    cookie_payload = _decode_user_cookie(token)

    assert set(cookie_payload) == {"sid"}
    record = session_store.get_session(cookie_payload["sid"])
    assert record is not None
    assert record["kind"] == "user"
    assert record["user_id"] == "google-sub-1"

    verified = auth_module.verify_session_token(token)
    assert verified["sub"] == "google-sub-1"
    assert verified["sid"] == cookie_payload["sid"]


def test_guest_session_cookie_contains_only_opaque_sid(session_store: AppFirestoreStore) -> None:
    import backend.auth as auth_module

    token = auth_module.issue_guest_session_token()
    cookie_payload = _decode_guest_cookie(token)

    assert set(cookie_payload) == {"sid"}
    record = session_store.get_session(cookie_payload["sid"])
    assert record is not None
    assert record["kind"] == "guest"
    assert record["user_id"] is None

    verified = auth_module.verify_guest_session_token(token)
    assert verified["mode"] == "guest"
    assert verified["sid"] == cookie_payload["sid"]


def test_revoked_user_session_is_rejected(session_store: AppFirestoreStore) -> None:
    import backend.auth as auth_module

    token = auth_module.issue_session_token("google-sub-2")
    assert auth_module.revoke_session_token(token) is True

    with pytest.raises(BadSignature):
        auth_module.verify_session_token(token)


def test_idle_timeout_is_enforced(session_store: AppFirestoreStore) -> None:
    import backend.auth as auth_module

    token = auth_module.issue_session_token("google-sub-3")
    sid = _decode_user_cookie(token)["sid"]
    old_seen = datetime.now(UTC) - timedelta(seconds=7200)
    session_store.touch_session(sid, last_seen_at=old_seen.replace(microsecond=0).isoformat())

    with pytest.raises(SignatureExpired):
        auth_module.verify_session_token(token)
