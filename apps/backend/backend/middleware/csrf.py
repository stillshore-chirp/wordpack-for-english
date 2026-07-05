from __future__ import annotations

from typing import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ..config import settings
from ..logging import logger


class CsrfProtectionMiddleware(BaseHTTPMiddleware):
    """Block browser cross-site unsafe requests before auth cookies are used."""

    _unsafe_methods = {"POST", "PUT", "PATCH", "DELETE"}
    _local_dev_origins = {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://testserver",
    }

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:  # type: ignore[override]
        if not getattr(settings, "csrf_protection_enabled", True):
            return await call_next(request)
        if request.method.upper() not in self._unsafe_methods:
            return await call_next(request)

        sec_fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
        if sec_fetch_site == "cross-site":
            return self._reject(request, reason="fetch_metadata_cross_site")

        origin = request.headers.get("origin")
        if origin and not self._is_allowed_origin(request, origin):
            return self._reject(request, reason="origin_mismatch", origin=origin)

        return await call_next(request)

    def _is_allowed_origin(self, request: Request, origin: str) -> bool:
        normalized = _normalize_origin(origin)
        if not normalized:
            return False
        allowed = {
            *_normalized_origins(getattr(settings, "csrf_trusted_origins", ())),
            *_normalized_origins(getattr(settings, "allowed_cors_origins", ())),
            *self._local_dev_origins,
            _normalize_origin(str(request.base_url).rstrip("/")),
        }
        return normalized in allowed

    @staticmethod
    def _reject(request: Request, *, reason: str, origin: str | None = None) -> JSONResponse:
        logger.warning(
            "csrf_request_denied",
            path=request.url.path,
            method=request.method,
            reason=reason,
            origin=origin,
            sec_fetch_site=request.headers.get("sec-fetch-site"),
            request_id=getattr(request.state, "request_id", None),
        )
        return JSONResponse(status_code=403, content={"detail": "CSRF check failed"})


def _normalize_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    parsed = urlsplit(origin.strip())
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _normalized_origins(values: object) -> set[str]:
    result: set[str] = set()
    try:
        candidates = list(values or ())
    except TypeError:
        candidates = [str(values)]
    for value in candidates:
        normalized = _normalize_origin(str(value))
        if normalized:
            result.add(normalized)
    return result
