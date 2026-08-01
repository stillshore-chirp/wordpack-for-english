from __future__ import annotations

import hashlib
import json
import os
import time
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Mapping

from structlog import contextvars as structlog_contextvars

from ..logging import logger
from .identity import PromptIdentity
from .types import CompletionResult

_MAX_PROVENANCE_BYTES = 8192


@contextmanager
def generation_workflow_context(workflow_id: str):
    structlog_contextvars.bind_contextvars(workflow_id=workflow_id)
    try:
        yield
    finally:
        structlog_contextvars.unbind_contextvars("workflow_id")


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()


def runtime_correlation() -> dict[str, str | None]:
    context = structlog_contextvars.get_contextvars()
    trace_raw = str(context.get("trace") or "").strip()
    trace_id = trace_raw.rsplit("/", 1)[-1] if trace_raw else None
    return {
        "request_id": str(context.get("request_id") or "").strip() or None,
        "workflow_id": str(context.get("workflow_id") or "").strip() or None,
        "trace_id": trace_id,
        "release": (
            os.getenv("LANGFUSE_RELEASE")
            or os.getenv("RELEASE")
            or os.getenv("DEPLOYMENT_VERSION")
        ),
        "git_sha": os.getenv("GIT_SHA") or os.getenv("TRIGGER_SHA"),
        "cloud_run_revision": os.getenv("K_REVISION"),
    }


def complete_typed(
    llm: object,
    prompt: str,
    *,
    identity: PromptIdentity,
    response_mode: str = "json",
) -> CompletionResult:
    """typed API が無い legacy test double も1回だけ呼び出して包む。"""

    complete_result = getattr(llm, "complete_result", None)
    if callable(complete_result):
        return complete_result(prompt, identity=identity, response_mode=response_mode)

    started = time.perf_counter()
    method_name = "complete_text" if response_mode == "plain" else "complete"
    method = getattr(llm, method_name, None)
    if not callable(method):
        method = getattr(llm, "complete", None)
    if not callable(method):
        raise RuntimeError("LLM provider does not support completion")
    content = str(method(prompt) or "")
    correlation = runtime_correlation()
    result = CompletionResult(
        content=content,
        provider="legacy",
        requested_model=str(identity.requested_parameters.get("model") or "") or None,
        resolved_model=str(identity.requested_parameters.get("model") or "") or None,
        requested_parameters=dict(identity.requested_parameters),
        effective_parameters=dict(identity.requested_parameters),
        latency_ms=int((time.perf_counter() - started) * 1000),
        prompt=identity,
        input_hash=content_hash(prompt),
        output_hash=content_hash(content),
        **correlation,
    )
    return result


def with_validation(
    result: CompletionResult,
    *,
    parse: bool | None = None,
    schema: bool | None = None,
    application: bool | None = None,
) -> CompletionResult:
    return replace(
        result,
        validation={"parse": parse, "schema": schema, "application": application},
    )


def _bounded(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k)[:80]: _bounded(v) for k, v in list(value.items())[:32]}
    if isinstance(value, (list, tuple)):
        return [_bounded(v) for v in list(value)[:32]]
    if isinstance(value, str):
        return value[:512]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:512]


def provenance_from_result(result: CompletionResult) -> dict[str, Any]:
    """raw prompt/output を含まない compact metadata を返す。"""

    prompt = result.prompt
    payload: dict[str, Any] = {
        "operation": prompt.operation if prompt else None,
        "prompt_id": prompt.prompt_id if prompt else None,
        "prompt_revision": prompt.prompt_revision if prompt else None,
        "schema_revision": prompt.schema_revision if prompt else None,
        "provider": result.provider,
        "requested_model": result.requested_model,
        "resolved_model": result.resolved_model,
        "requested_parameters": _bounded(result.requested_parameters),
        "effective_parameters": _bounded(result.effective_parameters),
        "fallback_profile": result.fallback_profile,
        "fallback_reason": result.fallback_reason,
        "failed_profiles": list(result.failed_profiles),
        "response_id": result.response_id,
        "status": result.response_status,
        "usage": {
            "input_tokens": result.usage.input_tokens,
            "cached_input_tokens": result.usage.cached_input_tokens,
            "output_tokens": result.usage.output_tokens,
            "reasoning_tokens": result.usage.reasoning_tokens,
            "total_tokens": result.usage.total_tokens,
        },
        "latency_ms": result.latency_ms,
        "attempt_count": result.attempt_count,
        "finish_info": result.finish_info,
        "incomplete_info": result.incomplete_info,
        "validation": dict(result.validation),
        "request_id": result.request_id,
        "workflow_id": result.workflow_id,
        "trace_id": result.trace_id,
        "release": result.release,
        "git_sha": result.git_sha,
        "cloud_run_revision": result.cloud_run_revision,
        "input_hash": result.input_hash,
        "output_hash": result.output_hash,
    }
    bounded = _bounded(payload)
    serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    if len(serialized.encode("utf-8")) > _MAX_PROVENANCE_BYTES:
        logger.warning("llm_provenance_size_limited", bytes=len(serialized.encode("utf-8")))
        bounded["requested_parameters"] = {"truncated": True}
        bounded["effective_parameters"] = {"truncated": True}
        serialized = json.dumps(bounded, ensure_ascii=False, sort_keys=True)
    if len(serialized.encode("utf-8")) > _MAX_PROVENANCE_BYTES:
        bounded = {
            key: bounded.get(key)
            for key in (
                "operation",
                "prompt_id",
                "prompt_revision",
                "schema_revision",
                "provider",
                "requested_model",
                "resolved_model",
                "fallback_profile",
                "fallback_reason",
                "response_id",
                "status",
                "usage",
                "latency_ms",
                "attempt_count",
                "validation",
                "request_id",
                "workflow_id",
                "trace_id",
                "release",
                "git_sha",
                "cloud_run_revision",
                "input_hash",
                "output_hash",
            )
        }
        bounded["metadata_truncated"] = True
    return bounded


def safe_provenance(result: CompletionResult) -> dict[str, Any] | None:
    try:
        return provenance_from_result(result)
    except Exception as exc:
        logger.warning("llm_provenance_serialization_failed", error_type=type(exc).__name__)
        return None


__all__ = [
    "complete_typed",
    "content_hash",
    "generation_workflow_context",
    "provenance_from_result",
    "runtime_correlation",
    "safe_provenance",
    "with_validation",
]
