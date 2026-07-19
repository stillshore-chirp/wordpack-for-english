from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol


class Clock(Protocol):
    def now_iso(self) -> str:
        raise NotImplementedError


class IdGenerator(Protocol):
    def new_id(self) -> str:
        raise NotImplementedError


class TaskScheduler(Protocol):
    def spawn(self, awaitable: Awaitable[object]) -> None:
        raise NotImplementedError


class AsyncCallable(Protocol):
    def __call__(self, *args: object, **kwargs: object) -> Awaitable[object]:
        raise NotImplementedError


TaskFactory = Callable[[], Awaitable[object]]
