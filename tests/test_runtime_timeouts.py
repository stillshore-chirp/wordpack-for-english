from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "backend"))
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8080")

from backend.app import middleware_stack  # noqa: E402
from backend.routers import config as config_router  # noqa: E402


class _RecordingApp:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    def add_middleware(self, middleware: object, **kwargs: object) -> None:
        self.calls.append((middleware, kwargs))


def test_http_middleware_uses_the_multi_call_flow_timeout(monkeypatch):
    app = _RecordingApp()

    middleware_stack._maybe_add_timeout_middleware(
        app,
        SimpleNamespace(llm_request_timeout_ms=1_500_000),
    )

    assert app.calls == [
        (
            middleware_stack.RequestTimeoutMiddleware,
            {
                "timeout": 1505,
                "excluded_paths": frozenset(
                    {
                        "/api/article/import",
                        "/api/article/generate_and_import",
                    }
                ),
            },
        )
    ]


def test_request_timeout_middleware_returns_504() -> None:
    async def _assert_timeout() -> None:
        messages: list[dict[str, object]] = []

        async def slow_app(scope, receive, send) -> None:
            await asyncio.sleep(0.02)

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            messages.append(message)

        middleware = middleware_stack.RequestTimeoutMiddleware(slow_app, timeout=0.001)
        await middleware(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/api/test",
                "raw_path": b"/api/test",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 504

    asyncio.run(_assert_timeout())


def test_request_timeout_middleware_skips_non_cancellable_sync_routes() -> None:
    async def _assert_excluded_route(path: str) -> None:
        messages: list[dict[str, object]] = []

        async def slow_app(scope, receive, send) -> None:
            await asyncio.sleep(0.01)
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [],
                }
            )
            await send({"type": "http.response.body", "body": b"ok"})

        async def receive() -> dict[str, object]:
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message: dict[str, object]) -> None:
            messages.append(message)

        middleware = middleware_stack.RequestTimeoutMiddleware(
            slow_app,
            timeout=0.001,
            excluded_paths={
                "/api/article/import",
                "/api/article/generate_and_import",
            },
        )
        await middleware(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 1234),
                "server": ("testserver", 80),
                "root_path": "",
            },
            receive,
            send,
        )
        assert messages[0]["type"] == "http.response.start"
        assert messages[0]["status"] == 200

    for path in ("/api/article/import", "/api/article/generate_and_import"):
        asyncio.run(_assert_excluded_route(path))


def test_runtime_config_separates_general_and_multi_call_flow_timeouts(monkeypatch):
    monkeypatch.setattr(
        config_router.settings,
        "request_timeout_ms",
        60_000,
    )
    monkeypatch.setattr(
        config_router.settings,
        "llm_request_timeout_ms",
        1_500_000,
    )

    config = config_router.get_runtime_config()
    assert config["request_timeout_ms"] == 60_000
    assert config["generation_request_timeout_ms"] == 1_500_000
