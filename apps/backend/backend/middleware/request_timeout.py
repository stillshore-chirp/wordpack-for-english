from __future__ import annotations

import asyncio
from collections.abc import Collection

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestTimeoutMiddleware:
    """Cancel an HTTP request that exceeds the configured end-to-end deadline."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        timeout: float,
        excluded_paths: Collection[str] = (),
    ) -> None:
        self.app = app
        self.timeout = max(0.001, float(timeout))
        self.excluded_paths = frozenset(excluded_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") in self.excluded_paths:
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, tracking_send),
                timeout=self.timeout,
            )
        except TimeoutError:
            if response_started:
                raise
            response = JSONResponse(
                status_code=504,
                content={
                    "detail": {
                        "error": "request_timeout",
                        "message": "Request exceeded the server processing deadline",
                    }
                },
            )
            await response(scope, receive, send)
