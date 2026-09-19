from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path
from typing import Any, Callable
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient

_TEST_SESSION_SECRET = "Y7mQ2nL8vR4pZ1xC6dK9sA3fT5gH8jW0"  # 32文字以上のテスト専用値
_TEST_EMULATOR_HOST = "127.0.0.1:8080"
_TEST_PROJECT_ID = "wordpack-integration-test"


def _ensure_firestore_emulator_ready(emulator_host: str) -> None:
    """Firestore エミュレータが起動済みであることを確認する。

    なぜ: 実クライアントでエミュレータ接続を検証するため、ローカルの任意実行では
    未起動をskipできる一方、CIの必須gateでは接続不能をfailureとして残す。
    """

    url = f"http://{emulator_host}/"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            response.read(1)
    except Exception:
        if os.environ.get("FIRESTORE_INTEGRATION_REQUIRED", "").strip().lower() in {
            "1",
            "true",
            "yes",
        }:
            pytest.fail(
                "Firestore emulator readiness failed; required integration gate cannot continue",
                pytrace=False,
            )
        pytest.skip("Firestore emulator readiness failed; optional integration skipped")


def _reload_backend_app(monkeypatch: pytest.MonkeyPatch) -> Any:
    """エミュレータ向けの環境変数を反映しつつ backend アプリを再ロードする。

    なぜ: backend.store は import 時に Firestore クライアントを初期化するため、
    環境変数を先に差し替えたうえでモジュールを再読み込みして接続先を固定する。
    """

    import importlib

    backend_root = Path(__file__).resolve().parents[2] / "apps" / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("STRICT_MODE", "false")
    monkeypatch.setenv("DISABLE_SESSION_AUTH", "true")
    monkeypatch.setenv("SESSION_SECRET_KEY", _TEST_SESSION_SECRET)
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", _TEST_EMULATOR_HOST)
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", _TEST_PROJECT_ID)
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", _TEST_PROJECT_ID)

    for name in list(sys.modules.keys()):
        if name == "backend" or name.startswith("backend."):
            sys.modules.pop(name)

    importlib.import_module("backend.config")
    importlib.import_module("backend.store")
    return importlib.import_module("backend.main")


@pytest.fixture()
def firestore_emulator_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Firestore エミュレータ接続用の環境変数を準備する。

    なぜ: テスト単位で接続先を固定し、他テストの設定と干渉しないようにする。
    """

    _ensure_firestore_emulator_ready(_TEST_EMULATOR_HOST)
    env = {
        "FIRESTORE_EMULATOR_HOST": _TEST_EMULATOR_HOST,
        "FIRESTORE_PROJECT_ID": _TEST_PROJECT_ID,
        "GOOGLE_CLOUD_PROJECT": _TEST_PROJECT_ID,
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return env


@pytest.fixture()
def api_client(monkeypatch: pytest.MonkeyPatch, firestore_emulator_env: dict[str, str]) -> TestClient:
    """Firestore エミュレータ接続済みの FastAPI TestClient を返す。"""

    app_module = _reload_backend_app(monkeypatch)
    return TestClient(app_module.app)


@pytest.mark.firestore_integration
def test_word_pack_create_persists_to_firestore_emulator(
    api_client: TestClient,
    firestore_emulator_env: dict[str, str],
) -> None:
    """API 呼び出しで保存した WordPack がエミュレータに永続化されることを確認する。"""

    response = api_client.post("/api/word/packs", json={"lemma": "integration"})
    assert response.status_code == 200

    payload = response.json()
    word_pack_id = payload.get("id")
    assert isinstance(word_pack_id, str)
    assert word_pack_id.startswith("wp:")

    from backend.store import AppFirestoreStore, store

    assert isinstance(store, AppFirestoreStore)
    stored = store.get_word_pack(word_pack_id)
    assert stored is not None
    lemma, data_json, created_at, updated_at = stored
    assert lemma == "integration"
    assert created_at <= updated_at

    stored_payload = json.loads(data_json)
    assert stored_payload.get("lemma") == "integration"
    assert stored_payload.get("confidence") == "low"

    client_options = getattr(store._client, "_client_options", None)
    api_endpoint = getattr(client_options, "api_endpoint", None)
    emulator_host = firestore_emulator_env["FIRESTORE_EMULATOR_HOST"]
    assert emulator_host in (api_endpoint or "")
    assert os.environ.get("FIRESTORE_EMULATOR_HOST") == emulator_host

    read_back = api_client.get(f"/api/word/packs/{word_pack_id}")
    assert read_back.status_code == 200
    read_payload = read_back.json()
    assert read_payload.get("lemma") == "integration"
    assert read_payload.get("sense_title")


def _raise_connection_refused(*_args: object, **_kwargs: object) -> Any:
    raise urllib.error.URLError(ConnectionRefusedError("connection refused"))


def _raise_timeout(*_args: object, **_kwargs: object) -> Any:
    raise TimeoutError("timed out")


def _raise_http_error(*_args: object, **_kwargs: object) -> Any:
    raise urllib.error.HTTPError(
        _TEST_EMULATOR_HOST,
        503,
        "synthetic emulator unavailable",
        {},
        None,
    )


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(_raise_connection_refused, id="connection-refused"),
        pytest.param(_raise_timeout, id="timeout"),
        pytest.param(_raise_http_error, id="http-error"),
    ],
)
@pytest.mark.parametrize("required", [True, False], ids=["required", "optional"])
def test_readiness_transport_failure_respects_gate_mode(
    monkeypatch: pytest.MonkeyPatch,
    failure: Callable[..., Any],
    required: bool,
) -> None:
    """Transport failures are failures only when the integration gate is required."""

    monkeypatch.setenv(
        "FIRESTORE_INTEGRATION_REQUIRED", "true" if required else "false"
    )
    monkeypatch.setattr(urllib.request, "urlopen", failure)
    expected = pytest.fail.Exception if required else pytest.skip.Exception
    expected_message = "required integration gate" if required else "optional integration"

    with pytest.raises(expected, match=expected_message):
        _ensure_firestore_emulator_ready(_TEST_EMULATOR_HOST)


def _closed_loopback_host() -> str:
    """Return an immediately closed loopback port for endpoint failure tests."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    return f"127.0.0.1:{port}"


@pytest.mark.parametrize(
    "failure_source",
    ["wrong-host-or-port", "emulator-process-exited"],
)
@pytest.mark.parametrize("required", [True, False], ids=["required", "optional"])
def test_closed_emulator_endpoint_respects_gate_mode(
    failure_source: str,
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
) -> None:
    """Wrong targets and an exited process share the closed-port failure contract."""

    del failure_source
    monkeypatch.setenv(
        "FIRESTORE_INTEGRATION_REQUIRED", "true" if required else "false"
    )
    expected = pytest.fail.Exception if required else pytest.skip.Exception
    expected_message = "required integration gate" if required else "optional integration"

    with pytest.raises(expected, match=expected_message):
        _ensure_firestore_emulator_ready(_closed_loopback_host())
