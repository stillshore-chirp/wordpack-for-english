from __future__ import annotations

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def debug_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """/_debug 系のレスポンスを検証するための TestClient を提供する。

    backend モジュールの配置（apps/backend 配下）を import path に追加したうえで、
    セッション認証を無効化して最小限の設定で FastAPI アプリを初期化する。
    """

    backend_root = Path(__file__).resolve().parents[1] / "apps" / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    monkeypatch.setenv("DISABLE_SESSION_AUTH", "true")
    monkeypatch.setenv(
        "SESSION_SECRET_KEY",
        "T3sTIngSeSsIoNkEyForDebugHeaders123456",
    )

    from backend.main import create_app

    app = create_app()
    return TestClient(app)


def test_debug_headers_echo_forwarding_information(debug_client: TestClient) -> None:
    """X-Forwarded-* と URL/クライアント IP のエコー内容を確認する。"""

    resp = debug_client.get(
        "/_debug/headers",
        headers={
            "host": "backend.internal",
            "x-forwarded-host": "public.example.com",
            "x-forwarded-proto": "https",
            "x-forwarded-for": "203.0.113.10",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["host"] == "backend.internal"
    assert body["x_forwarded_host"] == "public.example.com"
    assert body["x_forwarded_proto"] == "https"
    assert body["x_forwarded_for"] == "203.0.113.10"
    assert body["url"] == "http://backend.internal/_debug/headers"
    assert body["client_host"] == "testclient"


def test_debug_headers_shares_same_application(debug_client: TestClient) -> None:
    """/_debug/headers が /api 配下と同じアプリで提供されることを確認する。"""

    cfg = debug_client.get("/api/config")
    assert cfg.status_code == 200
    body = cfg.json()
    assert "request_timeout_ms" in body
    assert "generation_request_timeout_ms" in body
    assert "google_client_id" in body
