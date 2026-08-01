from __future__ import annotations

import os
import secrets


def prepare_backend_cli_environment() -> None:
    """Supply process-local settings required only by backend module imports."""

    os.environ.setdefault("SESSION_SECRET_KEY", secrets.token_urlsafe(32))


__all__ = ["prepare_backend_cli_environment"]
