from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.types import ASGIApp
from structlog import contextvars as structlog_contextvars

from ..logging import logger
from ..metrics import registry
from .cloud_trace import parse_cloud_trace_header
from .tracing import request_trace

try:
    from starlette.exceptions import TimeoutException  # type: ignore
except Exception:  # pragma: no cover - 互換目的のフォールバック
    TimeoutException = None  # type: ignore[assignment]


class AccessLogAndMetricsMiddleware(BaseHTTPMiddleware):
    """Emit structured request logs and capture latency/metrics for each call."""

    def __init__(self, app: ASGIApp, app_settings: Any | None = None) -> None:
        super().__init__(app)
        from ..config import settings

        self._settings = app_settings or settings

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:  # type: ignore[override]
        start = time.time()
        path = request.url.path
        method = request.method
        request_id = getattr(request.state, "request_id", None)
        if not request_id:
            request_id = uuid4().hex
            request.state.request_id = request_id
        structlog_contextvars.bind_contextvars(request_id=request_id)
        trace_log_fields = parse_cloud_trace_header(
            request.headers.get("x-cloud-trace-context"),
        )
        if trace_log_fields:
            structlog_contextvars.bind_contextvars(**trace_log_fields)
        client_ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "-")
        is_error = False
        is_timeout = False
        status_code: int | None = None
        error_type: str | None = None
        error_message: str | None = None
        input_payload: dict[str, Any] = {
            "path": path,
            "method": method,
            "query": dict(request.query_params) if request.query_params else {},
        }
        with request_trace(
            name=f"HTTP {method} {path}",
            user_id=request.headers.get("x-user-id"),
            metadata={
                "request_id": request_id,
                "client_ip": client_ip,
                "user_agent": ua,
                "path": path,
            },
            path=path,
        ) as ctx:
            trace_obj = ctx.get("trace") if isinstance(ctx, dict) else None  # type: ignore[assignment]
            try:
                if trace_obj is not None and hasattr(trace_obj, "set_attribute"):
                    trace_obj.set_attribute("input", str(input_payload)[:40000])  # type: ignore[call-arg]
                elif trace_obj is not None and hasattr(trace_obj, "update"):
                    trace_obj.update(input=input_payload)
            except Exception:  # pragma: no cover - 追跡失敗時も処理継続
                pass
            try:
                response = await call_next(request)
                status_code = getattr(response, "status_code", None)
                try:
                    output_payload = {
                        "status": status_code,
                        "content_type": response.headers.get("content-type"),
                        "content_length": response.headers.get("content-length"),
                    }
                    if trace_obj is not None and hasattr(trace_obj, "set_attribute"):
                        trace_obj.set_attribute("output", str(output_payload)[:40000])  # type: ignore[call-arg]
                    elif trace_obj is not None and hasattr(trace_obj, "update"):
                        trace_obj.update(output=output_payload)
                except Exception:  # pragma: no cover - 出力メタ記録失敗時
                    pass
                try:
                    if (
                        not is_error
                        and isinstance(status_code, int)
                        and status_code == 401
                    ):
                        is_error = True
                        error_type = error_type or "HTTPUnauthorized"
                        error_message = error_message or "HTTP 401 Unauthorized"
                    if isinstance(status_code, int) and status_code >= 500:
                        is_error = True
                        error_type = error_type or f"HTTP{status_code}"
                        error_message = error_message or f"HTTP {status_code} response"
                except Exception:  # pragma: no cover - ログ用補完に失敗しても本処理は継続
                    pass
                return response
            except Exception as exc:
                is_error = True
                status_code = getattr(exc, "status_code", 500) if hasattr(exc, "status_code") else 500
                error_type = exc.__class__.__name__
                raw_error_message = str(exc)
                error_message = (
                    raw_error_message
                    if len(raw_error_message) <= 200
                    else f"{raw_error_message[:197]}..."
                )
                if (
                    TimeoutException is not None and isinstance(exc, TimeoutException)
                ) or isinstance(exc, asyncio.TimeoutError):
                    is_timeout = True
                raise
            finally:
                request_id = getattr(request.state, "request_id", request_id)
                latency_ms = (time.time() - start) * 1000
                registry.record(path, latency_ms, is_error=is_error, is_timeout=is_timeout)
                log_method = logger.error if is_error else logger.info
                log_method(
                    "request_complete",
                    path=path,
                    method=method,
                    latency_ms=latency_ms,
                    is_error=is_error,
                    is_timeout=is_timeout,
                    status_code=status_code,
                    error_type=error_type,
                    error_message=error_message,
                    request_id=request_id,
                    client_ip=client_ip,
                    user_agent=ua,
                    **trace_log_fields,
                )
                if trace_log_fields:
                    structlog_contextvars.unbind_contextvars(*trace_log_fields.keys())
                structlog_contextvars.unbind_contextvars("request_id")
