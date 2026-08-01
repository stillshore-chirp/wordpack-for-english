from __future__ import annotations

import asyncio

from fastapi import Request
from starlette.responses import Response

from backend.middleware import RequestIDMiddleware


def test_request_id_middleware_reuses_outer_correlation_id() -> None:
    async def scenario() -> tuple[str, str | None]:
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/healthz",
                "headers": [],
                "query_string": b"",
                "scheme": "http",
                "server": ("testserver", 80),
                "client": ("testclient", 123),
            }
        )
        request.state.request_id = "outer-correlation-id"

        async def call_next(inner_request: Request) -> Response:
            assert inner_request.state.request_id == "outer-correlation-id"
            return Response(status_code=200)

        async def unused_app(_scope: object, _receive: object, _send: object) -> None:
            return None

        middleware = RequestIDMiddleware(unused_app)
        response = await middleware.dispatch(request, call_next)
        return request.state.request_id, response.headers.get("X-Request-ID")

    state_id, response_id = asyncio.run(scenario())

    assert state_id == "outer-correlation-id"
    assert response_id == "outer-correlation-id"
