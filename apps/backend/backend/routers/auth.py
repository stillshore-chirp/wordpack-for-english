from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from http import HTTPStatus

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from itsdangerous import BadSignature, SignatureExpired
from pydantic import BaseModel, Field

from ..auth import (
    guest_session_cookie_max_age,
    guest_session_cookie_names,
    issue_guest_session_token,
    issue_session_token,
    read_session_cookie,
    revoke_session_token,
    resolve_guest_session_cookie,
    resolve_session_cookie,
    session_cookie_names,
    verify_guest_session_token,
    verify_session_token,
)
from ..config import settings
from ..logging import logger
from ..store import store

router = APIRouter(tags=["auth"])
_google_request = google_requests.Request()


class GoogleAuthRequest(BaseModel):
    """Payload containing Google Identity Services credential fields."""

    id_token: str | None = Field(default=None, description="Legacy Google ID token")
    credential: str | None = Field(
        default=None, description="Google Identity Services credential"
    )
    g_csrf_token: str | None = Field(
        default=None, description="Google Identity Services CSRF token"
    )

    def token_value(self) -> str | None:
        return self.credential or self.id_token


class GoogleAuthResponse(BaseModel):
    """Response carrying the persisted user profile."""

    user: dict[str, str]


class GuestAuthResponse(BaseModel):
    """Response signaling that guest mode is active."""

    mode: str = Field(default="guest", description="Guest mode marker")


def _verify_google_id_token(token: str, audience: str, clock_skew_seconds: int) -> dict[str, object]:
    """Verify a Google ID token through google-auth and return its claims."""

    try:
        return id_token.verify_oauth2_token(
            token,
            _google_request,
            audience,
            clock_skew_in_seconds=clock_skew_seconds,
        )
    except TypeError:
        # Older google-auth versions do not accept clock_skew_in_seconds.
        return id_token.verify_oauth2_token(token, _google_request, audience)


@router.post("/api/auth/google", response_model=GoogleAuthResponse)
async def authenticate_with_google(payload: GoogleAuthRequest, request: Request) -> JSONResponse:
    """Verify Google ID token, persist the user, and issue a signed session cookie."""

    if not settings.google_client_id:
        logger.error(
            "google_auth_failed",
            user_id=None,
            reason="missing_client_id",
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Google authentication is not configured",
        )
    if not settings.session_secret_key:
        logger.error(
            "google_auth_failed",
            user_id=None,
            reason="missing_session_secret",
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Session secret key is not configured",
        )

    token = payload.token_value()
    if not token:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Google credential is required",
        )

    if payload.credential is not None or payload.g_csrf_token is not None:
        cookie_csrf_token = read_session_cookie(request, "g_csrf_token")
        if (
            not payload.g_csrf_token
            or not cookie_csrf_token
            or payload.g_csrf_token != cookie_csrf_token
        ):
            logger.warning(
                "google_auth_failed",
                user_id=None,
                reason="csrf_token_mismatch",
            )
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Google CSRF token mismatch",
            )

    try:
        # 許容する時計ずれ（nbf/iat/exp の境界緩和）。古い google-auth 互換のため TypeError 時は従来呼び出しにフォールバック。
        _skew = max(0, int(getattr(settings, "google_clock_skew_seconds", 0) or 0))
        id_info = _verify_google_id_token(
            token,
            settings.google_client_id,
            _skew,
        )
    except ValueError as exc:
        logger.warning(
            "google_auth_failed",
            user_id=None,
            reason="invalid_token",
            error=repr(exc),
        )
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="Invalid ID token") from exc

    google_sub = id_info.get("sub")
    email = id_info.get("email")
    display_name = id_info.get("name") or id_info.get("email")
    hosted_domain = id_info.get("hd") or id_info.get("hostedDomain")
    email_hash = _hash_for_log(email)
    user_id_hash = _hash_for_log(str(google_sub) if google_sub else None)
    email_verified = id_info.get("email_verified")

    missing_claims = [
        claim
        for claim, value in (("sub", google_sub), ("email", email))
        if not value
    ]

    if not google_sub or not email or not display_name:
        logger.warning(
            "google_auth_failed",
            user_id_hash=user_id_hash,
            reason="missing_claims",
            missing_claims=missing_claims,
            email_hash=email_hash,
        )
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="ID token is missing required claims")

    # Google から検証済みフラグが降りてこない場合は、サポートとの調査時に
    # ハッシュ化済みメールと拒否理由を突合できるように記録して即座に拒否する。
    if email_verified is not True:
        logger.warning(
            "google_auth_denied",
            user_id_hash=user_id_hash,
            reason="email_unverified",
            email_hash=email_hash,
        )
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Google account email must be verified",
        )

    allowed_hd = (settings.google_allowed_hd or "").strip()
    if allowed_hd and hosted_domain != allowed_hd:
        logger.warning(
            "google_auth_denied",
            user_id_hash=user_id_hash,
            reason="domain_mismatch",
            hosted_domain=hosted_domain,
            allowed_domain=allowed_hd,
            email_hash=email_hash,
        )
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Google account domain is not allowed")

    # 許可されたメールアドレス一覧が設定されている場合は、完全一致で照合して拒否理由を明示的に記録する。
    allowlisted_emails = getattr(settings, "admin_email_allowlist", ())
    if allowlisted_emails:
        normalised_email = email.strip().lower()
        if normalised_email not in allowlisted_emails:
            logger.warning(
                "google_auth_denied",
                user_id_hash=user_id_hash,
                reason="email_not_allowlisted",
                hosted_domain=hosted_domain,
                email_hash=email_hash,
                allowlist_size=len(allowlisted_emails),
            )
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="Google account email is not allowlisted",
            )

    user = store.record_user_login(
        google_sub=google_sub,
        email=email,
        display_name=display_name,
        login_at=datetime.now(UTC),
    )
    session_token = issue_session_token(google_sub, request=request)

    response = JSONResponse(status_code=HTTPStatus.OK, content={"user": user})
    for cookie_name in session_cookie_names():
        response.set_cookie(
            key=cookie_name,
            value=session_token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            max_age=_session_cookie_max_age(),
        )
    request.state.user = user
    request.state.user_id = google_sub
    # 成功ログは個人情報を直接出力しないよう `_log_google_auth_success` へ委譲する。
    _log_google_auth_success(google_sub, email, display_name)
    return response


@router.post("/api/auth/guest", response_model=GuestAuthResponse)
async def authenticate_as_guest(request: Request) -> JSONResponse:
    """Issue a signed guest session cookie for read-only access."""

    if not settings.session_secret_key:
        logger.error(
            "guest_auth_failed",
            user_id=None,
            reason="missing_session_secret",
        )
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Session secret key is not configured",
        )

    guest_token = issue_guest_session_token(request=request)
    response = JSONResponse(status_code=HTTPStatus.OK, content={"mode": "guest"})
    for cookie_name in guest_session_cookie_names():
        response.set_cookie(
            key=cookie_name,
            value=guest_token,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
            max_age=guest_session_cookie_max_age(),
        )
    request.state.guest = True
    logger.info(
        "guest_session_issued",
        user_id=None,
        reason="guest_mode",
    )
    return response


@router.post("/api/auth/logout", status_code=HTTPStatus.NO_CONTENT)
async def logout(request: Request, response: Response) -> Response:
    """Invalidate auth cookies so subsequent requests become anonymous.

    新メンバー向け補足: フロントエンドはバックエンドにログアウトを通知し、ここで
    HttpOnly Cookie を削除することでセッションを終了させる。ゲスト閲覧モードも
    HttpOnly Cookie を使うため、このハンドラーで通常セッションと同じように失効させる。"""

    user_id, logout_mode = _resolve_logout_context(request)
    _revoke_all_present_sessions(request)

    response.status_code = HTTPStatus.NO_CONTENT
    for cookie_name in dict.fromkeys((*session_cookie_names(), *guest_session_cookie_names())):
        response.delete_cookie(
            key=cookie_name,
            httponly=True,
            secure=settings.session_cookie_secure,
            samesite="lax",
        )
    logger.info(
        "logout_completed",
        user_id_hash=_hash_for_log(user_id),
        reason=logout_mode,
    )
    return response


def _revoke_all_present_sessions(request: Request) -> None:
    seen: set[tuple[str, str]] = set()
    for cookie_name in session_cookie_names():
        token = read_session_cookie(request, cookie_name)
        if token and ("user", token) not in seen:
            seen.add(("user", token))
            revoke_session_token(token)
    for cookie_name in guest_session_cookie_names():
        token = read_session_cookie(request, cookie_name)
        if token and ("guest", token) not in seen:
            seen.add(("guest", token))
            revoke_session_token(token, guest=True)


def _resolve_logout_context(request: Request) -> tuple[str | None, str]:
    """Return log context for an authenticated or guest logout request."""

    _cookie_name, session_token = resolve_session_cookie(request)
    session_invalid = False
    if session_token:
        try:
            payload = verify_session_token(session_token)
        except (SignatureExpired, BadSignature, RuntimeError):
            session_invalid = True
        else:
            revoke_session_token(session_token)
            sub = payload.get("sub") if isinstance(payload, dict) else None
            if not sub:
                session_invalid = True
            else:
                return str(sub), "logout"

    guest_token = resolve_guest_session_cookie(request)
    if guest_token:
        try:
            payload = verify_guest_session_token(guest_token)
        except (SignatureExpired, BadSignature, RuntimeError):
            return None, "guest_logout_invalid"
        if not isinstance(payload, dict) or payload.get("mode") != "guest":
            return None, "guest_logout_invalid"
        revoke_session_token(guest_token, guest=True)
        request.state.guest = True
        return None, "guest_logout"

    if session_invalid:
        return None, "logout_invalid_session"

    raise HTTPException(
        status_code=HTTPStatus.UNAUTHORIZED,
        detail="Session or guest cookie is missing",
    )


def _session_cookie_max_age() -> int:
    """Resolve the cookie lifetime from configuration."""

    try:
        return max(60, int(settings.session_max_age_seconds))
    except (TypeError, ValueError):  # pragma: no cover - defensive fallback
        return 60 * 60 * 24 * 14


def _hash_for_log(value: str | None) -> str | None:
    """Hash sensitive identifiers before logging to avoid leaking PII."""

    if not value:
        return None
    # Google アカウントのメールアドレスなどの PII を直接出力しないよう、
    # SHA-256 の先頭12文字に圧縮してロギングする。SRE がインシデント時に
    # 該当アカウントを特定できる粒度を残しつつ漏洩リスクを抑える意図。
    digest = hashlib.sha256(value.lower().encode("utf-8")).hexdigest()
    return digest[:12]


def _log_google_auth_success(
    user_id: str,
    email: str | None,
    display_name: str | None,
) -> None:
    """Log sanitized Google auth success events for Cloud Logging compliance.

    新規メンバーでも誤って平文の識別子を記録しないよう、この関数経由で
    ログを出力する。必要なときは `_hash_for_log` を再利用して display_name も
    ハッシュ化する方針を徹底する。
    """

    logger.info(
        "google_auth_succeeded",
        user_id_hash=_hash_for_log(user_id),
        reason="authenticated",
        email_hash=_hash_for_log(email),
        display_name_hash=_hash_for_log(display_name),
    )
