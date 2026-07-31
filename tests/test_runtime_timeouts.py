from __future__ import annotations

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
    marker = object()
    monkeypatch.setattr(middleware_stack, "TimeoutMiddleware", marker)
    app = _RecordingApp()

    middleware_stack._maybe_add_timeout_middleware(
        app,
        SimpleNamespace(llm_request_timeout_ms=1_500_000),
    )

    assert app.calls == [(marker, {"timeout": 1505})]


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
