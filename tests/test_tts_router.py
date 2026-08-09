from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable, Iterator

import httpx
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "apps" / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.main import create_app
from backend.routers import tts

try:
    from openai import AuthenticationError  # type: ignore
except Exception:  # pragma: no cover - openai 未導入環境
    AuthenticationError = None  # type: ignore[assignment]


class _DummyResponse:
    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    def iter_bytes(self) -> Iterator[bytes]:
        yield from self._chunks

    def close(self) -> None:
        self.closed = True


class _DummyClient:
    def __init__(self, factory: Callable[..., object]) -> None:
        self.audio = type(
            "_Audio",
            (),
            {
                "speech": type(
                    "_Speech",
                    (),
                    {"create": staticmethod(lambda **kwargs: factory(**kwargs))},
                )()
            },
        )()


def test_tts_synth_streams_audio(monkeypatch) -> None:
    original_client = tts.client
    dummy_response = _DummyResponse([b"foo", b"bar"])
    tts.client = _DummyClient(lambda **_: dummy_response)  # type: ignore[assignment]
    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/tts", json={"text": "Hello", "voice": "verse"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("audio/mpeg")
        assert response.content == b"foobar"
        assert dummy_response.closed is True
    finally:
        tts.client = original_client  # type: ignore[assignment]


def test_tts_accepts_text_above_former_500_character_limit(monkeypatch) -> None:
    """保存済み長文を旧UI上限で拒否しないことを検証する。"""

    original_client = tts.client
    dummy_response = _DummyResponse([b"audio"])
    captured: dict[str, object] = {}

    def _capture(**kwargs: object) -> object:
        captured.update(kwargs)
        return dummy_response

    tts.client = _DummyClient(_capture)  # type: ignore[assignment]
    try:
        text = "a" * 501
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/tts", json={"text": text})
        assert response.status_code == 200
        assert response.content == b"audio"
        assert captured["input"] == text
    finally:
        tts.client = original_client  # type: ignore[assignment]


def test_tts_rejects_text_above_provider_request_limit(monkeypatch) -> None:
    """Speech APIの単発上限超過時に 413 が返却されることを検証する。"""

    original_client = tts.client
    tts.client = None  # type: ignore[assignment]
    try:
        over_limit = "a" * (tts.TTS_API_REQUEST_MAX_LENGTH + 1)
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/tts", json={"text": over_limit})
        assert response.status_code == 413
        detail = response.json()["detail"]
        assert detail["error"] == "tts_text_too_long"
        assert detail["max_length"] == tts.TTS_API_REQUEST_MAX_LENGTH
        assert str(tts.TTS_API_REQUEST_MAX_LENGTH) in detail["message"]
    finally:
        tts.client = original_client  # type: ignore[assignment]


def test_tts_synth_unconfigured(monkeypatch) -> None:
    original_client = tts.client
    tts.client = None  # type: ignore[assignment]
    monkeypatch.setattr(tts.settings, "openai_api_key", None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    try:
        app = create_app()
        with TestClient(app) as client:
            response = client.post("/api/tts", json={"text": "Hi"})
        assert response.status_code == 500
        assert response.json()["detail"].startswith("OpenAI client is not configured")
    finally:
        tts.client = original_client  # type: ignore[assignment]


def test_init_client_reads_settings(monkeypatch) -> None:
    class _SpyClient:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    monkeypatch.setattr(tts, "OpenAI", _SpyClient)
    monkeypatch.setattr(tts.settings, "openai_api_key", "from-settings")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    client = tts._init_client()
    assert isinstance(client, _SpyClient)
    assert client.api_key == "from-settings"


def test_tts_authentication_error(monkeypatch, caplog, capfd) -> None:
    if AuthenticationError is None:  # pragma: no cover - openai 未導入環境
        return

    original_client = tts.client

    response_obj = httpx.Response(401, request=httpx.Request("POST", "https://example.com"))

    def _raise_auth(**_: object) -> object:
        raise AuthenticationError(message="bad key", response=response_obj, body=None)

    tts.client = _DummyClient(_raise_auth)  # type: ignore[assignment]
    try:
        app = create_app()
        with caplog.at_level("WARNING"):
            with TestClient(app) as client:
                response = client.post("/api/tts", json={"text": "Hello", "voice": "alloy"})
        assert response.status_code == 502
        assert response.json()["detail"] == "OpenAI authentication failed"
        entries = []
        for record in caplog.records:
            message = record.getMessage()
            if not isinstance(message, str):
                continue
            try:
                payload = json.loads(message)
            except json.JSONDecodeError:
                continue
            entries.append(payload)
        captured = capfd.readouterr()
        assert any(entry.get("event") == "tts_request_failed" for entry in entries) or (
            "tts_request_failed" in captured.err
        )
    finally:
        tts.client = original_client  # type: ignore[assignment]
