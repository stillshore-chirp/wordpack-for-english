from __future__ import annotations

from typing import Any, Callable, Mapping

from ...logging import logger


def resolve_flow_exception(
    mapping: Mapping[str, Callable[..., Exception]] | None,
    key: str,
    **kwargs: Any,
) -> Exception | None:
    if not mapping:
        return None
    handler = mapping.get(key)
    if handler is None:
        return None
    try:
        return handler(**kwargs)
    except Exception as exc:
        logger.warning(
            "wordpack_error_mapping_failed",
            key=key,
            error=str(exc),
        )
        return None


def handle_flow_runtime_error(
    exc: RuntimeError,
    *,
    lemma: str,
    strict_mode: bool,
    error_mapping: Mapping[str, Callable[..., Exception]] | None,
) -> None:
    msg = str(exc)
    low = msg.lower()
    if "failed to parse llm json" in low and strict_mode:
        custom_exc = resolve_flow_exception(error_mapping, "llm_json_parse", lemma=lemma)
        if custom_exc:
            raise custom_exc from exc
        raise RuntimeError("LLM output JSON parse failed (strict mode)") from exc

    if "reason_code=" in msg:
        if "reason_code=TIMEOUT" in msg:
            custom_exc = resolve_flow_exception(error_mapping, "timeout", lemma=lemma)
            if custom_exc:
                raise custom_exc from exc
        if "reason_code=RATE_LIMIT" in msg:
            custom_exc = resolve_flow_exception(error_mapping, "rate_limit", lemma=lemma)
            if custom_exc:
                raise custom_exc from exc
        if (
            "reason_code=AUTH" in msg
            or "invalid api key" in low
            or "unauthorized" in low
        ):
            custom_exc = resolve_flow_exception(error_mapping, "auth", lemma=lemma)
            if custom_exc:
                raise custom_exc from exc
        if "reason_code=PARAM_UNSUPPORTED" in msg:
            custom_exc = resolve_flow_exception(
                error_mapping, "param_unsupported", lemma=lemma
            )
            if custom_exc:
                raise custom_exc from exc

    reason_code = getattr(exc, "reason_code", None)
    diagnostics = getattr(exc, "diagnostics", None)
    if reason_code == "EMPTY_CONTENT":
        custom_exc = resolve_flow_exception(
            error_mapping,
            "empty_content",
            lemma=lemma,
            diagnostics=diagnostics or {},
        )
        if custom_exc:
            raise custom_exc from exc
        raise RuntimeError(
            "WordPack generation returned empty content (no senses/examples)"
        ) from exc
