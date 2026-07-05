from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config import settings
from backend.middleware.csrf import CsrfProtectionMiddleware


def _client() -> TestClient:
    app = FastAPI()
    app.add_middleware(CsrfProtectionMiddleware)

    @app.post("/unsafe")
    async def unsafe() -> dict[str, bool]:
        return {"ok": True}

    return TestClient(app)


def test_fetch_metadata_cross_site_unsafe_request_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(settings, "csrf_protection_enabled", True)
    response = _client().post("/unsafe", headers={"sec-fetch-site": "cross-site"})

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF check failed"


def test_origin_mismatch_unsafe_request_is_blocked(monkeypatch) -> None:
    monkeypatch.setattr(settings, "csrf_protection_enabled", True)
    monkeypatch.setattr(settings, "csrf_trusted_origins", ("https://app.example",))

    response = _client().post("/unsafe", headers={"origin": "https://evil.example"})

    assert response.status_code == 403
    assert response.json()["detail"] == "CSRF check failed"


def test_trusted_origin_unsafe_request_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "csrf_protection_enabled", True)
    monkeypatch.setattr(settings, "csrf_trusted_origins", ("https://app.example",))

    response = _client().post("/unsafe", headers={"origin": "https://app.example"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_trusted_origin_can_satisfy_cross_site_fetch_metadata(monkeypatch) -> None:
    monkeypatch.setattr(settings, "csrf_protection_enabled", True)
    monkeypatch.setattr(settings, "csrf_trusted_origins", ("https://app.example",))

    response = _client().post(
        "/unsafe",
        headers={
            "origin": "https://app.example",
            "sec-fetch-site": "cross-site",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_missing_browser_origin_is_allowed_for_non_browser_clients(monkeypatch) -> None:
    monkeypatch.setattr(settings, "csrf_protection_enabled", True)

    response = _client().post("/unsafe")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
