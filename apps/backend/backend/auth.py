from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .authorization.principal import ANONYMOUS_PRINCIPAL, Principal
from .config import settings
from .logging import logger
from .store import store

_SESSION_SALT = "wordpack.session"
_GUEST_SESSION_SALT = "wordpack.guest_session"
_FIREBASE_SESSION_COOKIE = "__session"


def _build_serializer(salt: str = _SESSION_SALT) -> URLSafeTimedSerializer:
    """Construct a serializer for signing and verifying session tokens."""

    secret = settings.session_secret_key.strip()
    if not secret:
        raise RuntimeError("SESSION_SECRET_KEY is not configured")
    return URLSafeTimedSerializer(secret, salt=salt)


def _session_max_age() -> int:
    try:
        max_age = int(getattr(settings, "session_max_age_seconds", 0))
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        max_age = 0
    return max(60, max_age or 60 * 60 * 24 * 14)


def _guest_session_max_age() -> int:
    try:
        max_age = int(getattr(settings, "guest_session_max_age_seconds", 0))
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        max_age = 0
    return max(60, max_age or 60 * 60 * 24)


def _session_idle_timeout(kind: str) -> int:
    key = (
        "guest_session_idle_timeout_seconds"
        if kind == "guest"
        else "session_idle_timeout_seconds"
    )
    fallback = _guest_session_max_age() if kind == "guest" else _session_max_age()
    try:
        configured = int(getattr(settings, key, fallback))
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        configured = fallback
    return max(60, configured or fallback)


def _last_seen_update_interval() -> int:
    try:
        configured = int(
            getattr(settings, "session_last_seen_update_interval_seconds", 300)
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        configured = 300
    return max(0, configured)


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _hash_session_context(value: str | None) -> str | None:
    if not value:
        return None
    pepper = settings.session_secret_key.strip()
    material = f"{pepper}:{value}".encode("utf-8", errors="ignore")
    return hashlib.sha256(material).hexdigest()


def _request_user_agent_hash(request: Request | None) -> str | None:
    if request is None:
        return None
    return _hash_session_context(request.headers.get("user-agent"))


def _request_ip_hash(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return _hash_session_context(request.client.host)


def guest_session_cookie_max_age() -> int:
    return _guest_session_max_age()


def _create_session_record(
    *,
    kind: str,
    user_id: str | None,
    max_age_seconds: int,
    request: Request | None,
) -> str:
    sid = secrets.token_urlsafe(32)
    issued_at = _now()
    expires_at = issued_at + timedelta(seconds=max_age_seconds)
    payload: dict[str, Any] = {
        "sid": sid,
        "kind": kind,
        "user_id": user_id,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "last_seen_at": issued_at.isoformat(),
        "revoked_at": None,
        "user_agent_hash": _request_user_agent_hash(request),
        "created_ip_hash": _request_ip_hash(request),
    }
    create_session = getattr(store, "create_session", None)
    if not callable(create_session):
        raise RuntimeError("session store is not configured")
    create_session(payload)
    return sid


def issue_session_token(google_sub: str, request: Request | None = None) -> str:
    """Generate a signed opaque session token for an authenticated user."""

    serializer = _build_serializer(_SESSION_SALT)
    sid = _create_session_record(
        kind="user",
        user_id=google_sub,
        max_age_seconds=_session_max_age(),
        request=request,
    )
    return serializer.dumps({"sid": sid})


def issue_guest_session_token(request: Request | None = None) -> str:
    """Generate a signed opaque guest session token for read-only browsing."""

    serializer = _build_serializer(_GUEST_SESSION_SALT)
    sid = _create_session_record(
        kind="guest",
        user_id=None,
        max_age_seconds=_guest_session_max_age(),
        request=request,
    )
    return serializer.dumps({"sid": sid})


def _touch_session_if_needed(sid: str, record: Mapping[str, Any], *, now: datetime) -> None:
    last_seen_at = _parse_dt(record.get("last_seen_at"))
    interval = _last_seen_update_interval()
    if last_seen_at is not None and (now - last_seen_at).total_seconds() < interval:
        return
    touch_session = getattr(store, "touch_session", None)
    if callable(touch_session):
        touch_session(sid, last_seen_at=now.isoformat())


def _validate_session_record(
    payload: Mapping[str, Any],
    *,
    expected_kind: str,
) -> dict[str, Any]:
    sid = str(payload.get("sid") or "").strip()
    if not sid:
        raise BadSignature("session id missing")
    get_session = getattr(store, "get_session", None)
    if not callable(get_session):
        raise RuntimeError("session store is not configured")
    record = get_session(sid)
    if not isinstance(record, Mapping):
        raise BadSignature("session record not found")
    if record.get("kind") != expected_kind:
        raise BadSignature("session kind mismatch")
    if record.get("revoked_at"):
        raise BadSignature("session revoked")

    now = _now()
    expires_at = _parse_dt(record.get("expires_at"))
    if expires_at is None or now > expires_at:
        raise SignatureExpired("session expired")
    last_seen_at = _parse_dt(record.get("last_seen_at"))
    if last_seen_at is not None:
        idle_seconds = (now - last_seen_at).total_seconds()
        if idle_seconds > _session_idle_timeout(expected_kind):
            raise SignatureExpired("session idle timeout")

    _touch_session_if_needed(sid, record, now=now)
    user_id = record.get("user_id")
    result = dict(payload)
    result["sid"] = sid
    result["kind"] = expected_kind
    result["session_id"] = sid
    if isinstance(user_id, str) and user_id:
        result["sub"] = user_id
        result["user_id"] = user_id
    if expected_kind == "guest":
        result["mode"] = "guest"
    return result


def verify_session_token(token: str) -> dict[str, Any]:
    """Decode a signed user session token and validate server-side state."""

    serializer = _build_serializer(_SESSION_SALT)
    payload = serializer.loads(token, max_age=_session_max_age())
    if not isinstance(payload, Mapping):
        raise BadSignature("invalid session payload")
    if payload.get("sub"):
        # Short-term compatibility for legacy signed payloads generated before
        # server-side session records were introduced.
        legacy = dict(payload)
        legacy.setdefault("kind", "user")
        legacy.setdefault("session_id", legacy.get("sid"))
        legacy.setdefault("user_id", legacy.get("sub"))
        return legacy
    return _validate_session_record(payload, expected_kind="user")


def verify_guest_session_token(token: str) -> dict[str, Any]:
    """Decode a signed guest session token and validate server-side state."""

    serializer = _build_serializer(_GUEST_SESSION_SALT)
    payload = serializer.loads(token, max_age=_guest_session_max_age())
    if not isinstance(payload, Mapping):
        raise BadSignature("invalid guest session payload")
    if payload.get("mode") == "guest" and payload.get("gid"):
        legacy = dict(payload)
        legacy.setdefault("kind", "guest")
        legacy.setdefault("session_id", legacy.get("gid"))
        return legacy
    return _validate_session_record(payload, expected_kind="guest")


def revoke_session_token(token: str, *, guest: bool = False) -> bool:
    """Best-effort server-side revocation for an incoming session token."""

    try:
        payload = verify_guest_session_token(token) if guest else verify_session_token(token)
    except (SignatureExpired, BadSignature, RuntimeError):
        return False
    sid = payload.get("sid") or payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        return False
    revoke_session = getattr(store, "revoke_session", None)
    if not callable(revoke_session):
        return False
    return bool(revoke_session(sid, revoked_at=_now_iso()))


def _session_log_context(
    request: Request, *, reason: str, user_id: str | None
) -> dict[str, object]:
    client_ip = request.client.host if request.client else "unknown"
    return {
        "user_id": user_id,
        "reason": reason,
        "path": request.url.path,
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def read_session_cookie(request: Request, cookie_name: str) -> str | None:
    """Read a cookie even when other Cookie header entries are non-RFC values."""

    try:
        value = request.cookies.get(cookie_name)  # type: ignore[assignment]
    except Exception:  # pragma: no cover - defensive guard
        value = None
    if value:
        return value  # type: ignore[return-value]

    raw_header = request.headers.get("cookie") or request.headers.get("Cookie")
    if not raw_header:
        return None
    for part in raw_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, raw_value = part.split("=", 1)
        if name.strip() == cookie_name:
            return raw_value.strip()
    return None


def session_cookie_names() -> tuple[str, ...]:
    configured = (settings.session_cookie_name or "wp_session").strip()
    primary = configured or "wp_session"
    names = [primary]
    if _FIREBASE_SESSION_COOKIE not in names:
        names.append(_FIREBASE_SESSION_COOKIE)
    return tuple(dict.fromkeys(names))


def guest_session_cookie_name() -> str:
    configured = (settings.guest_session_cookie_name or "wp_guest").strip()
    return configured or "wp_guest"


def guest_session_cookie_names() -> tuple[str, ...]:
    primary = guest_session_cookie_name()
    names = [primary]
    if _FIREBASE_SESSION_COOKIE not in names:
        names.append(_FIREBASE_SESSION_COOKIE)
    return tuple(dict.fromkeys(names))


def resolve_session_cookie(request: Request) -> tuple[str | None, str | None]:
    for cookie_name in session_cookie_names():
        token = read_session_cookie(request, cookie_name)
        if token:
            return cookie_name, token
    return None, None


def resolve_guest_session_cookie(request: Request) -> str | None:
    for cookie_name in guest_session_cookie_names():
        token = read_session_cookie(request, cookie_name)
        if token:
            return token
    return None


def _guest_log_context(request: Request, *, reason: str) -> dict[str, object]:
    client_ip = request.client.host if request.client else "unknown"
    return {
        "reason": reason,
        "path": request.url.path,
        "client_ip": client_ip,
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _principal_from_user(user: Mapping[str, str], payload: Mapping[str, Any]) -> Principal:
    user_id = str(payload.get("sub") or payload.get("user_id") or user.get("google_sub") or "")
    return Principal(
        kind="user",
        user_id=user_id or None,
        email=user.get("email"),
        display_name=user.get("display_name"),
        session_id=str(payload.get("sid") or payload.get("session_id") or "") or None,
    )


def _attach_user_state(
    request: Request, user: Mapping[str, str], payload: Mapping[str, Any]
) -> Principal:
    principal = _principal_from_user(user, payload)
    request.state.user = dict(user)
    request.state.user_id = principal.user_id
    request.state.principal = principal
    request.state.guest = False
    return principal


def _attach_guest_state(request: Request, payload: Mapping[str, Any]) -> Principal:
    principal = Principal(
        kind="guest",
        session_id=str(payload.get("sid") or payload.get("session_id") or "") or None,
    )
    request.state.guest = True
    request.state.principal = principal
    return principal


def _resolve_authenticated_user(
    request: Request,
    *,
    log_missing: bool,
    allow_invalid_session: bool = False,
) -> dict[str, str] | None:
    _cookie_name, raw_token = resolve_session_cookie(request)
    if not raw_token:
        if log_missing:
            logger.warning(
                "session_validation_failed",
                **_session_log_context(request, reason="missing_cookie", user_id=None),
            )
        return None

    try:
        payload = verify_session_token(raw_token)
    except SignatureExpired as exc:
        session_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
        logger.warning(
            "session_validation_failed",
            **_session_log_context(request, reason="expired", user_id=None),
        )
        if allow_invalid_session:
            request.state.session_validation_error = session_error
            return None
        raise session_error from exc
    except BadSignature as exc:
        session_error = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )
        logger.warning(
            "session_validation_failed",
            **_session_log_context(request, reason="bad_signature", user_id=None),
        )
        if allow_invalid_session:
            request.state.session_validation_error = session_error
            return None
        raise session_error from exc
    except RuntimeError as exc:
        logger.error(
            "session_validation_failed",
            **_session_log_context(request, reason="configuration_error", user_id=None),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Session configuration error",
        ) from exc

    sub = payload.get("sub") if isinstance(payload, Mapping) else None
    if not sub:
        logger.warning(
            "session_validation_failed",
            **_session_log_context(request, reason="missing_sub", user_id=None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session payload",
        )

    user = store.get_user_by_google_sub(str(sub))
    if user is None:
        logger.warning(
            "session_validation_failed",
            **_session_log_context(request, reason="user_not_found", user_id=str(sub)),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    _attach_user_state(request, user, payload)
    return user


async def get_current_user(request: Request) -> dict[str, str]:
    user = _resolve_authenticated_user(request, log_missing=True)
    if user is not None:
        return user
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session cookie is missing",
    )


async def get_current_user_principal(request: Request) -> Principal:
    await get_current_user(request)
    principal = getattr(request.state, "principal", None)
    if isinstance(principal, Principal) and principal.is_user:
        return principal
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User session is required",
    )


def principal_from_request(request: Request) -> Principal:
    if settings.disable_session_auth:
        return Principal(kind="user", user_id="test-user")
    principal = getattr(request.state, "principal", None)
    return principal if isinstance(principal, Principal) else ANONYMOUS_PRINCIPAL


async def get_current_user_or_guest(request: Request) -> dict[str, str]:
    user = _resolve_authenticated_user(
        request,
        log_missing=False,
        allow_invalid_session=True,
    )
    if user is not None:
        return user

    guest_token = resolve_guest_session_cookie(request)
    if not guest_token:
        session_error = getattr(request.state, "session_validation_error", None)
        if isinstance(session_error, HTTPException):
            raise session_error
        logger.warning(
            "guest_session_invalid",
            **_guest_log_context(request, reason="missing_cookie"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session or guest cookie is missing",
        )

    try:
        payload = verify_guest_session_token(guest_token)
    except SignatureExpired as exc:
        session_error = getattr(request.state, "session_validation_error", None)
        if isinstance(session_error, HTTPException):
            raise session_error
        logger.warning(
            "guest_session_invalid",
            **_guest_log_context(request, reason="expired"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Guest session expired",
        ) from exc
    except BadSignature as exc:
        session_error = getattr(request.state, "session_validation_error", None)
        if isinstance(session_error, HTTPException):
            raise session_error
        logger.warning(
            "guest_session_invalid",
            **_guest_log_context(request, reason="bad_signature"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guest session token",
        ) from exc
    except RuntimeError as exc:
        logger.error(
            "guest_session_invalid",
            **_guest_log_context(request, reason="configuration_error"),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Guest session configuration error",
        ) from exc

    if isinstance(payload, Mapping) and payload.get("mode") != "guest":
        logger.warning(
            "guest_session_invalid",
            **_guest_log_context(request, reason="missing_guest_mode"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid guest session payload",
        )

    _attach_guest_state(request, payload)
    return {"mode": "guest"}


async def get_current_principal_or_guest(request: Request) -> Principal:
    await get_current_user_or_guest(request)
    principal = getattr(request.state, "principal", None)
    return principal if isinstance(principal, Principal) else ANONYMOUS_PRINCIPAL
