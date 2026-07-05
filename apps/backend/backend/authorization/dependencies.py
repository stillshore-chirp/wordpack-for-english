from __future__ import annotations

from fastapi import Request

from ..auth import get_current_user_principal
from ..config import settings
from .permissions import Permission
from .policies import ensure_user_write_allowed
from .principal import Principal


def require_user_permission(permission: Permission):
    """Build a FastAPI dependency that resolves a user Principal.

    The current permission enum is intentionally explicit even though all unsafe
    writes currently share the same user-only rule. Keeping the permission at the
    call site prevents future endpoints from silently bypassing policy review.
    """

    async def _dependency(
        request: Request,
    ) -> Principal:
        _ = permission
        if settings.disable_session_auth:
            test_principal = Principal(kind="user", user_id="test-user")
            request.state.principal = test_principal
            request.state.user_id = test_principal.user_id
            return test_principal
        principal = await get_current_user_principal(request)
        ensure_user_write_allowed(principal)
        return principal

    return _dependency
