from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..config import settings
from .errors import forbidden, not_found
from .principal import Principal


@dataclass(frozen=True)
class ResourceVisibility:
    """Minimal policy input for content guarded by owner and guest-public flags."""

    exists: bool
    guest_public: bool = False
    owner_user_id: str | None = None
    not_found_detail: str = "Resource not found"


def owner_user_id_from_mapping(payload: Mapping[str, Any] | None) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    owner = payload.get("owner_user_id")
    if isinstance(owner, str) and owner.strip():
        return owner.strip()
    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        nested_owner = metadata.get("owner_user_id")
        if isinstance(nested_owner, str) and nested_owner.strip():
            return nested_owner.strip()
    return None


def ensure_read_allowed(principal: Principal, visibility: ResourceVisibility) -> None:
    """Raise 404 when a principal must not learn that the resource exists."""

    if not visibility.exists:
        raise not_found(visibility.not_found_detail)

    if principal.is_guest or principal.is_anonymous:
        if visibility.guest_public:
            return
        raise not_found(visibility.not_found_detail)

    if principal.is_user:
        enforce_owner = bool(getattr(settings, "enforce_owner_scoping", False))
        owner_user_id = visibility.owner_user_id
        if enforce_owner and owner_user_id != principal.user_id:
            raise not_found(visibility.not_found_detail)
        if owner_user_id and owner_user_id != principal.user_id and enforce_owner:
            raise not_found(visibility.not_found_detail)
        return

    raise not_found(visibility.not_found_detail)


def ensure_user_write_allowed(
    principal: Principal,
    *,
    owner_user_id: str | None = None,
    not_found_detail: str = "Resource not found",
) -> None:
    """Require a signed user principal and optionally enforce resource ownership."""

    if principal.is_guest:
        raise forbidden("Guest mode cannot perform write operations")
    if not principal.is_user:
        raise forbidden("User session is required")

    enforce_owner = bool(getattr(settings, "enforce_owner_scoping", False))
    if enforce_owner and owner_user_id != principal.user_id:
        raise not_found(not_found_detail)
