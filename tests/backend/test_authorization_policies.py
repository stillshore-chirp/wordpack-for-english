from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.authorization.policies import (
    ResourceVisibility,
    ensure_read_allowed,
    ensure_user_write_allowed,
)
from backend.authorization.principal import Principal
from backend.config import settings


def test_guest_can_read_guest_public_resource() -> None:
    principal = Principal(kind="guest", session_id="guest-session")

    ensure_read_allowed(
        principal,
        ResourceVisibility(exists=True, guest_public=True, not_found_detail="Not found"),
    )


def test_guest_private_read_is_hidden_as_404() -> None:
    principal = Principal(kind="guest", session_id="guest-session")

    with pytest.raises(HTTPException) as exc_info:
        ensure_read_allowed(
            principal,
            ResourceVisibility(
                exists=True,
                guest_public=False,
                not_found_detail="WordPack not found",
            ),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "WordPack not found"


def test_owner_scope_defaults_to_legacy_shared_for_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enforce_owner_scoping", False)
    principal = Principal(kind="user", user_id="user-a")

    ensure_read_allowed(
        principal,
        ResourceVisibility(exists=True, guest_public=False, owner_user_id=None),
    )


def test_owner_scope_can_hide_foreign_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "enforce_owner_scoping", True)
    principal = Principal(kind="user", user_id="user-a")

    with pytest.raises(HTTPException) as exc_info:
        ensure_read_allowed(
            principal,
            ResourceVisibility(
                exists=True,
                guest_public=False,
                owner_user_id="user-b",
                not_found_detail="Quiz not found",
            ),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Quiz not found"


def test_guest_write_is_forbidden() -> None:
    principal = Principal(kind="guest", session_id="guest-session")

    with pytest.raises(HTTPException) as exc_info:
        ensure_user_write_allowed(principal)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Guest mode cannot perform write operations"
