from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


PrincipalKind = Literal["anonymous", "guest", "user"]


@dataclass(frozen=True)
class Principal:
    """Request principal resolved from signed, server-side session state."""

    kind: PrincipalKind
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None
    session_id: str | None = None

    @property
    def is_user(self) -> bool:
        return self.kind == "user" and bool(self.user_id)

    @property
    def is_guest(self) -> bool:
        return self.kind == "guest"

    @property
    def is_anonymous(self) -> bool:
        return self.kind == "anonymous"


ANONYMOUS_PRINCIPAL = Principal(kind="anonymous")
