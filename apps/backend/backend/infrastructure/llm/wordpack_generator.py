from __future__ import annotations

from functools import partial
from typing import Any, Callable, Mapping

import anyio

from ...config import settings
from ...flows.word_pack import WordPackFlow
from ...logging import logger
from ...models.word import WordPack
from ...providers import get_llm_provider
from ...application.wordpack.errors import handle_flow_runtime_error


def get_override_value(source: object, key: str) -> Any:
    if hasattr(source, key):
        return getattr(source, key)
    if isinstance(source, Mapping):
        return source.get(key)
    return None


def build_llm_info(overrides: object) -> dict[str, Any]:
    model = get_override_value(overrides, "model") or settings.llm_model
    params: str | None = None
    try:
        parts: list[str] = []
        reasoning = get_override_value(overrides, "reasoning") or {}
        if isinstance(reasoning, Mapping):
            effort = reasoning.get("effort")
            if effort:
                parts.append(f"reasoning.effort={effort}")
        text_opts = get_override_value(overrides, "text") or {}
        if isinstance(text_opts, Mapping):
            verbosity = text_opts.get("verbosity")
            if verbosity:
                parts.append(f"text.verbosity={verbosity}")
        params = ";".join(parts) if parts else None
    except Exception:
        params = None
    return {"model": model, "params": params}


async def run_wordpack_flow(
    *,
    lemma: str,
    req_opts: object,
    scope: Any,
    error_mapping: Mapping[str, Callable[..., Exception]] | None = None,
    http_error_mapping: Mapping[str, Callable[..., Exception]] | None = None,
) -> tuple[WordPack, dict[str, Any]]:
    llm = get_llm_provider(
        model_override=get_override_value(req_opts, "model"),
        reasoning_override=get_override_value(req_opts, "reasoning"),
        text_override=get_override_value(req_opts, "text"),
    )
    llm_info = build_llm_info(req_opts)
    flow = WordPackFlow(chroma_client=None, llm=llm, llm_info=llm_info)
    try:
        word_pack = await anyio.to_thread.run_sync(
            partial(
                flow.run,
                lemma,
                pronunciation_enabled=get_override_value(req_opts, "pronunciation_enabled")
                if get_override_value(req_opts, "pronunciation_enabled") is not None
                else True,
                regenerate_scope=scope,
            )
        )
    except RuntimeError as exc:
        handle_flow_runtime_error(
            exc,
            lemma=lemma,
            strict_mode=settings.strict_mode,
            error_mapping=error_mapping or http_error_mapping,
        )
        raise

    try:
        setattr(word_pack, "llm_model", llm_info.get("model"))
        setattr(word_pack, "llm_params", llm_info.get("params"))
    except Exception as exc:
        logger.debug(
            "wordpack_llm_metadata_assignment_skipped",
            error_type=exc.__class__.__name__,
        )
    return word_pack, llm_info
