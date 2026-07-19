from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApplicationError(Exception):
    code: str
    message: str
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message


class NotFoundError(ApplicationError):
    def __init__(self, message: str, *, code: str = "not_found") -> None:
        super().__init__(code=code, message=message)


class InvalidInputError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_input",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code=code, message=message, details=details)
