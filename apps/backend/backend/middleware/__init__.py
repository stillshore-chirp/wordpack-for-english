from __future__ import annotations

import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from typing import Awaitable, Callable, Iterable

from fastapi import Request
from itsdangerous import BadSignature, SignatureExpired
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ..auth import (
    resolve_guest_session_cookie,
    resolve_session_cookie,
    verify_guest_session_token,
    verify_session_token,
)
from ..config import settings
from ..logging import logger
from .csrf import CsrfProtectionMiddleware

# Forwarded host validation middleware lives in a dedicated module to keep
# host header handling isolated from other cross-cutting middleware concerns.
from .host import ForwardedHostTrustedHostMiddleware

__all__ = [
    "ForwardedHostTrustedHostMiddleware",
    "SecurityHeadersMiddleware",
    "RequestIDMiddleware",
    "RateLimitMiddleware",
    "GuestWriteBlockMiddleware",
    "CsrfProtectionMiddleware",
]


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach strict security headers to every HTTP response before it leaves the API.

    なぜ: API レスポンスから HSTS や CSP 等のヘッダが欠落すると、HTTPS 化済みでも
    ダウングレード攻撃やクリックジャッキング、想定外の外部ドメインからのリソース
    読み込みを許してしまう。共通ミドルウェアで一括設定し、`.env` から許可オリジンを
    管理できるようにすることで、セキュリティ制御と運用負荷を両立させる。
    """

    def __init__(self, app) -> None:
        super().__init__(app)
        self._headers = self._build_header_map()

    @staticmethod
    def _merge_sources(*groups: Iterable[str]) -> tuple[str, ...]:
        """Merge multiple CSP source tuples while preserving order and removing duplicates."""

        merged: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for candidate in group:
                if not candidate or candidate in seen:
                    continue
                seen.add(candidate)
                merged.append(candidate)
        return tuple(merged)

    def _build_hsts_value(self) -> str:
        """Construct the Strict-Transport-Security header value based on settings."""

        max_age = max(0, int(settings.security_hsts_max_age_seconds))
        directives = [f"max-age={max_age}"]
        if settings.security_hsts_include_subdomains:
            directives.append("includeSubDomains")
        if settings.security_hsts_preload:
            directives.append("preload")
        return "; ".join(directives)

    def _build_csp_value(self) -> str:
        """Compose the Content-Security-Policy directive string from configured sources."""

        default_sources = settings.security_csp_default_src or ("'self'",)
        connect_sources = (
            settings.security_csp_connect_src
            if settings.security_csp_connect_src
            else default_sources
        )
        # Swagger UI などのスタイル適用に必要な inline CSS を許可しつつ、
        # データ URI のみを追加許可することで XSS の攻撃面を最小化する。
        style_sources = self._merge_sources(default_sources, ("'unsafe-inline'",))
        img_sources = self._merge_sources(default_sources, ("data:",))
        font_sources = self._merge_sources(default_sources, ("data:",))
        script_sources = default_sources

        directives = [
            ("default-src", default_sources),
            ("connect-src", connect_sources),
            ("img-src", img_sources),
            ("script-src", script_sources),
            ("style-src", style_sources),
            ("font-src", font_sources),
            ("frame-ancestors", ("'none'",)),
            ("object-src", ("'none'",)),
            ("base-uri", ("'self'",)),
            ("form-action", ("'self'",)),
        ]

        parts: list[str] = []
        for directive, sources in directives:
            if not sources:
                continue
            joined_sources = " ".join(sources)
            parts.append(f"{directive} {joined_sources}")
        return "; ".join(parts)

    def _build_header_map(self) -> dict[str, str]:
        """Prepare the static header map applied to every response."""

        return {
            "Strict-Transport-Security": self._build_hsts_value(),
            "Content-Security-Policy": self._build_csp_value(),
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        response = await call_next(request)
        for header_name, value in self._headers.items():
            response.headers[header_name] = value
        return response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign a request ID to each incoming request and expose it in headers.

    - Sets `request.state.request_id`
    - Adds `X-Request-ID` to the response headers
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        try:
            response.headers["X-Request-ID"] = request_id
        except Exception:
            # Some response types may not allow header mutation after body start
            pass
        return response


class GuestWriteBlockMiddleware(BaseHTTPMiddleware):
    """Reject write requests when a signed guest session is present.

    なぜ: ゲスト閲覧モードは読み取り専用を前提としており、誤って
    生成・削除 API を呼び出した場合でも安全に拒否してデータ更新を防ぐ。
    """

    _write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    _allowlisted_paths = {"/api/auth/guest", "/api/auth/google", "/api/auth/logout"}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        if request.method.upper() not in self._write_methods:
            return await call_next(request)

        path = request.url.path
        if path in self._allowlisted_paths:
            return await call_next(request)

        _cookie_name, session_token = resolve_session_cookie(request)
        # なぜ: 空のセッショントークンを検証すると署名検証例外に誤って流れるため、
        #       実トークンがある場合のみ検証してゲスト Cookie の判定へ進める。
        if session_token:
            try:
                verify_session_token(session_token)
                return await call_next(request)
            except (SignatureExpired, BadSignature, RuntimeError):
                pass

        guest_token = resolve_guest_session_cookie(request)
        if not guest_token:
            return await call_next(request)

        try:
            verify_guest_session_token(guest_token)
        except (SignatureExpired, BadSignature, RuntimeError):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        logger.warning(
            "guest_write_denied",
            path=path,
            method=request.method,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(
            status_code=403,
            content={"detail": "Guest mode cannot perform write operations"},
        )


class _TokenBucket:
    """Thread-safe token bucket that refills to capacity every fixed interval (seconds)."""

    def __init__(self, capacity: int, refill_interval_sec: float) -> None:
        self.capacity = max(1, capacity)
        self.tokens = self.capacity
        self.refill_interval = max(1.0, float(refill_interval_sec))
        self.last_refill = time.time()
        self._lock = threading.Lock()

    def allow(self) -> tuple[bool, int]:
        """Consume one token if available and return the remaining count."""
        now = time.time()
        with self._lock:
            elapsed = now - self.last_refill
            if elapsed >= self.refill_interval:
                self.tokens = self.capacity
                self.last_refill = now
            if self.tokens > 0:
                self.tokens -= 1
                return True, self.tokens
            return False, 0


@dataclass
class _TrackedBucket:
    """Bundle a token bucket with its last access timestamp for eviction control."""

    bucket: _TokenBucket
    last_seen: float


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting per IP and per authenticated session using token buckets.

    なぜ: セッション Cookie を検証したユーザー単位でバケットを割り当て、
    任意ヘッダ偽装による制限回避を防ぐ。同時にバケットの最終利用時刻を追跡し、
    長時間アクセスのないキーを捨てることでメモリ使用量を抑える。
    """

    def __init__(
        self,
        app,
        *,
        ip_capacity_per_minute: int,
        user_capacity_per_minute: int,
        user_bucket_ttl_seconds: float = 15 * 60,
        max_user_buckets: int = 10_000,
    ) -> None:
        super().__init__(app)
        self._ip_capacity = max(1, int(ip_capacity_per_minute))
        self._user_capacity = max(1, int(user_capacity_per_minute))
        self._ip_buckets: dict[str, _TokenBucket] = {}
        self._user_buckets: OrderedDict[str, _TrackedBucket] = OrderedDict()
        self._lock = threading.Lock()
        self._anon_bucket_key = "anon"
        self._user_bucket_ttl = max(1.0, float(user_bucket_ttl_seconds))
        self._max_user_buckets = max(1, int(max_user_buckets))

    def _get_ip_bucket(self, key: str) -> _TokenBucket:
        with self._lock:
            if key not in self._ip_buckets:
                self._ip_buckets[key] = _TokenBucket(
                    capacity=self._ip_capacity,
                    refill_interval_sec=60.0,
                )
            return self._ip_buckets[key]

    def _prune_user_buckets(self, now: float) -> None:
        """Remove stale buckets and trim the OrderedDict to the configured max."""

        expired_keys = [
            key
            for key, entry in self._user_buckets.items()
            if now - entry.last_seen > self._user_bucket_ttl
        ]
        for key in expired_keys:
            self._user_buckets.pop(key, None)
        while len(self._user_buckets) >= self._max_user_buckets:
            # OrderedDict preserves insertion order; pop oldest entries first.
            self._user_buckets.popitem(last=False)

    def _get_user_bucket(self, key: str, now: float) -> _TokenBucket:
        with self._lock:
            self._prune_user_buckets(now)
            entry = self._user_buckets.get(key)
            if entry is None:
                entry = _TrackedBucket(
                    bucket=_TokenBucket(
                        capacity=self._user_capacity,
                        refill_interval_sec=60.0,
                    ),
                    last_seen=now,
                )
                self._user_buckets[key] = entry
            else:
                entry.last_seen = now
                self._user_buckets.move_to_end(key, last=True)
            return entry.bucket

    def _resolve_user_key(self, request: Request, client_ip: str) -> tuple[str, bool]:
        """Resolve the logical session identifier from the signed cookie."""

        _, raw_token = resolve_session_cookie(request)
        if not raw_token:
            logger.debug("rate_limit_session_missing", client_ip=client_ip)
            return self._anon_bucket_key, False

        try:
            payload = verify_session_token(raw_token)
        except SignatureExpired:
            logger.debug(
                "rate_limit_session_invalid",
                reason="expired",
                client_ip=client_ip,
            )
            return self._anon_bucket_key, False
        except BadSignature:
            logger.debug(
                "rate_limit_session_invalid",
                reason="bad_signature",
                client_ip=client_ip,
            )
            return self._anon_bucket_key, False
        except RuntimeError:
            logger.error(
                "rate_limit_session_invalid",
                reason="configuration_error",
                client_ip=client_ip,
            )
            return self._anon_bucket_key, False
        except Exception:  # pragma: no cover - defensive guard for unexpected errors
            logger.debug(
                "rate_limit_session_invalid",
                reason="unexpected_error",
                client_ip=client_ip,
            )
            return self._anon_bucket_key, False

        if isinstance(payload, dict):
            for key in ("sub", "user_id", "session_id", "sid"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value, True

        logger.debug(
            "rate_limit_session_invalid",
            reason="missing_session_identity",
            client_ip=client_ip,
        )
        return self._anon_bucket_key, False

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        # Identify caller
        client_ip = request.client.host if request.client else "unknown"
        user_key, is_authenticated = self._resolve_user_key(request, client_ip)
        now = time.time()
        ip_bucket = self._get_ip_bucket(client_ip)
        ok_ip, remaining_ip = ip_bucket.allow()
        if not ok_ip:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too Many Requests (per IP)"},
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit-Ip": str(self._ip_capacity),
                    "X-RateLimit-Remaining-Ip": str(remaining_ip),
                },
            )

        ok_user = True
        remaining_user: int | None = None
        if is_authenticated:
            user_bucket = self._get_user_bucket(user_key, now)
            ok_user, remaining_user = user_bucket.allow()

        if not ok_user:
            detail = (
                "Too Many Requests (per User)"
                if is_authenticated
                else "Too Many Requests (per Session)"
            )
            headers = {
                "Retry-After": "60",
                "X-RateLimit-Limit-Ip": str(self._ip_capacity),
                "X-RateLimit-Remaining-Ip": str(remaining_ip),
            }
            if is_authenticated:
                headers["X-RateLimit-Limit-User"] = str(self._user_capacity)
                headers["X-RateLimit-Remaining-User"] = str(remaining_user)
            return JSONResponse(
                status_code=429,
                content={"detail": detail},
                headers=headers,
            )

        response = await call_next(request)
        # Optionally expose current remaining counts (best-effort)
        try:
            response.headers.setdefault("X-RateLimit-Limit-Ip", str(self._ip_capacity))
            response.headers.setdefault("X-RateLimit-Remaining-Ip", str(remaining_ip))
            if is_authenticated:
                response.headers.setdefault(
                    "X-RateLimit-Limit-User", str(self._user_capacity)
                )
                response.headers.setdefault(
                    "X-RateLimit-Remaining-User", str(remaining_user)
                )
        except Exception:
            pass
        return response
