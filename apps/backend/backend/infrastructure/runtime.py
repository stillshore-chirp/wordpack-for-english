from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from datetime import UTC, datetime
from uuid import uuid4


class SystemClock:
    def now_iso(self) -> str:
        return datetime.now(UTC).isoformat()


class UuidHexGenerator:
    def new_id(self) -> str:
        return uuid4().hex


class PrefixedUuidGenerator:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def new_id(self) -> str:
        return f"{self._prefix}{uuid4().hex}"


class AsyncioTaskScheduler:
    def spawn(self, awaitable: Awaitable[object]) -> None:
        asyncio.create_task(awaitable)
