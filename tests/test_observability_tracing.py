from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from backend.observability import tracing


class _Observation:
    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)


class _LangfuseV4:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.observations: list[_Observation] = []

    @contextmanager
    def start_as_current_observation(self, **kwargs: Any):
        observation = _Observation()
        self.calls.append(kwargs)
        self.observations.append(observation)
        yield observation


def test_request_trace_and_span_use_langfuse_v4_observation_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _LangfuseV4()
    propagated: list[dict[str, Any]] = []

    @contextmanager
    def fake_propagate_attributes(**kwargs: Any):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(tracing, "_langfuse_client", client)
    monkeypatch.setattr(tracing, "propagate_attributes", fake_propagate_attributes)

    metadata = {"path": "/api/example"}
    with tracing.request_trace(
        name="request", user_id="user-1", metadata=metadata
    ) as trace_context:
        assert trace_context["trace"] is client.observations[0]
        with tracing.span(
            trace=trace_context["trace"],
            name="child",
            input={"prompt": "hello"},
            metadata={"model": "test"},
        ) as child:
            assert child is client.observations[1]

    assert propagated == [
        {
            "user_id": "user-1",
            "metadata": metadata,
            "trace_name": "request",
        }
    ]
    assert client.calls == [
        {
            "name": "request",
            "as_type": "span",
            "metadata": metadata,
        },
        {
            "name": "child",
            "as_type": "span",
            "input": "{'prompt': 'hello'}",
            "metadata": {"model": "test"},
        },
    ]
    assert "duration_ms" in client.observations[0].updates[-1]["metadata"]
    assert "duration_ms" in client.observations[1].updates[-1]["metadata"]


def test_langfuse_v4_observations_record_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _LangfuseV4()

    @contextmanager
    def fake_propagate_attributes(**_kwargs: Any):
        yield

    monkeypatch.setattr(tracing, "_langfuse_client", client)
    monkeypatch.setattr(tracing, "propagate_attributes", fake_propagate_attributes)

    with pytest.raises(RuntimeError, match="boom"):
        with tracing.request_trace(name="request"):
            raise RuntimeError("boom")

    error_update = client.observations[0].updates[0]
    assert error_update["level"] == "ERROR"
    assert error_update["status_message"] == "boom"
    final_metadata = client.observations[0].updates[-1]["metadata"]
    assert final_metadata["error"] == "boom"
    assert "duration_ms" in final_metadata


def test_langfuse_v4_child_observation_records_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _LangfuseV4()

    @contextmanager
    def fake_propagate_attributes(**_kwargs: Any):
        yield

    monkeypatch.setattr(tracing, "_langfuse_client", client)
    monkeypatch.setattr(tracing, "propagate_attributes", fake_propagate_attributes)

    with tracing.request_trace(name="request") as trace_context:
        with pytest.raises(ValueError, match="child failed"):
            with tracing.span(trace=trace_context["trace"], name="child"):
                raise ValueError("child failed")

    child_updates = client.observations[1].updates
    assert child_updates[0]["level"] == "ERROR"
    assert child_updates[0]["status_message"] == "child failed"
    assert child_updates[-1]["metadata"]["error"] == "child failed"
