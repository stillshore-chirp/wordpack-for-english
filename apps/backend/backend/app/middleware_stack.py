from __future__ import annotations

import inspect
from typing import Any

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from ..middleware import (
    CsrfProtectionMiddleware,
    GuestWriteBlockMiddleware,
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
from ..middleware.host import ForwardedHostTrustedHostMiddleware
from ..middleware.request_timeout import RequestTimeoutMiddleware
from ..observability import AccessLogAndMetricsMiddleware

_PROXY_MIDDLEWARE_PARAM = (
    "forwarded_allow_ips"
    if "forwarded_allow_ips"
    in inspect.signature(ProxyHeadersMiddleware.__init__).parameters
    else "trusted_hosts"
)

_NON_CANCELLABLE_SYNC_GENERATION_PATHS = frozenset(
    {
        "/api/article/import",
        "/api/article/generate_and_import",
    }
)


def _maybe_add_timeout_middleware(app: FastAPI, app_settings: Any) -> None:
    request_timeout_ms = getattr(
        app_settings,
        "llm_request_timeout_ms",
        1_500_000,
    )
    http_timeout_sec = max(
        1,
        int((request_timeout_ms + 5000) / 1000),
    )
    app.add_middleware(
        RequestTimeoutMiddleware,
        timeout=http_timeout_sec,
        # 互換用の同期フローは、イベントループをブロックするか worker thread 内で
        # 保存処理を続けるため、asyncio の期限では安全に停止できない。アプリUIは
        # 非同期ジョブを使い、同期互換ルートは Cloud Run の期限を最終境界にする。
        excluded_paths=_NON_CANCELLABLE_SYNC_GENERATION_PATHS,
    )


def configure_middleware(app: FastAPI, app_settings: Any) -> None:
    configured_proxies = [value for value in app_settings.trusted_proxy_ips if value]
    if not configured_proxies:
        configured_proxies = ["127.0.0.1"]
    proxy_argument = (
        configured_proxies[0]
        if len(configured_proxies) == 1
        else ",".join(configured_proxies)
    )
    configured_hosts = list(app_settings.allowed_hosts) or ["*"]
    configured_origins = list(app_settings.allowed_cors_origins)
    allow_credentials = bool(configured_origins)
    if not configured_origins:
        configured_origins = ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _maybe_add_timeout_middleware(app, app_settings)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(GuestWriteBlockMiddleware)
    app.add_middleware(CsrfProtectionMiddleware)
    # Middleware stack (inner -> outer):
    # RequestID -> GuestWriteBlock -> CsrfProtection -> AccessLog -> RateLimit
    # -> ForwardedHostTrustedHost -> SecurityHeaders -> ProxyHeaders.
    app.add_middleware(AccessLogAndMetricsMiddleware, app_settings=app_settings)
    app.add_middleware(
        RateLimitMiddleware,
        ip_capacity_per_minute=app_settings.rate_limit_per_min_ip,
        user_capacity_per_minute=app_settings.rate_limit_per_min_user,
    )
    app.add_middleware(
        ForwardedHostTrustedHostMiddleware,
        allowed_hosts=configured_hosts,
        trusted_proxy_ips=configured_proxies,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        ProxyHeadersMiddleware,
        **{_PROXY_MIDDLEWARE_PARAM: proxy_argument},
    )
