"""LLM プロバイダと Langfuse 連携を司るモジュール。"""

from __future__ import annotations

import contextvars
import time
from concurrent.futures import TimeoutError as FuturesTimeout
from contextlib import contextmanager
from dataclasses import replace
from typing import Any, Callable, Iterator, Optional

from ..config import settings
from ..llm_models import (
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TEXT_VERBOSITY,
    ensure_supported_llm_model,
)
from ..logging import logger
from ..llmops.completion import content_hash, runtime_correlation
from ..llmops.identity import PromptIdentity
from ..llmops.types import CompletionResult, TokenUsage
from ..observability import get_langfuse, span
from . import _get_llm_executor, _get_llm_instance, _set_llm_instance

try:  # pragma: no cover - ネットワーク依存の外部SDK
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover - 任意依存
    OpenAI = None  # type: ignore


_PROVIDER_ATTEMPT_OBSERVER: contextvars.ContextVar[
    Callable[[int], None] | None
] = contextvars.ContextVar("provider_attempt_observer", default=None)


class _LLMBase:
    """LLM クライアントが実装すべき最小インターフェース。"""

    def complete(self, prompt: str) -> str:  # pragma: no cover - interface definition
        raise NotImplementedError

    def complete_text(self, prompt: str) -> str:  # pragma: no cover - interface definition
        return self.complete(prompt)

    def complete_result(
        self,
        prompt: str,
        *,
        identity: PromptIdentity,
        response_mode: str = "json",
    ) -> CompletionResult:  # pragma: no cover - interface definition
        started = time.perf_counter()
        content = self.complete_text(prompt) if response_mode == "plain" else self.complete(prompt)
        return CompletionResult(
            content=content,
            provider="legacy",
            requested_model=None,
            resolved_model=None,
            prompt=identity,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_hash=content_hash(prompt),
            output_hash=content_hash(content),
            **runtime_correlation(),
        )


class _LocalEchoLLM(_LLMBase):
    """外部依存が利用できない環境でのフォールバック LLM。"""

    def complete(self, prompt: str) -> str:
        logger.info(
            "llm_complete_call",
            provider="local",
            model="echo",
            prompt_chars=len(prompt),
        )
        out = ""
        logger.info(
            "llm_complete_result",
            provider="local",
            model="echo",
            content_chars=len(out),
        )
        return out

    def complete_text(self, prompt: str) -> str:
        return self.complete(prompt)

    def complete_result(
        self,
        prompt: str,
        *,
        identity: PromptIdentity,
        response_mode: str = "json",
    ) -> CompletionResult:
        started = time.perf_counter()
        content = self.complete_text(prompt) if response_mode == "plain" else self.complete(prompt)
        return CompletionResult(
            content=content,
            provider="local",
            requested_model="echo",
            resolved_model="echo",
            requested_parameters=dict(identity.requested_parameters),
            effective_parameters=dict(identity.requested_parameters),
            prompt=identity,
            latency_ms=int((time.perf_counter() - started) * 1000),
            input_hash=content_hash(prompt),
            output_hash=content_hash(content),
            **runtime_correlation(),
        )


def _prepare_span_input(model: str, prompt: str) -> dict[str, Any]:
    """Langfuse スパンに記録する入力情報を生成する。"""

    if getattr(settings, "langfuse_log_full_prompt", False):
        maxc = int(getattr(settings, "langfuse_prompt_max_chars", 40000))
        payload: dict[str, Any] = {
            "model": model,
            "prompt_chars": len(prompt),
            "prompt": prompt[: max(0, maxc)],
        }
        payload["prompt_sha256"] = content_hash(prompt)
        return payload
    return {
        "model": model,
        "prompt_chars": len(prompt),
        "prompt_sha256": content_hash(prompt),
    }


@contextmanager
def _langfuse_span(name: str, model: str, prompt: str) -> Iterator[Any]:
    """Langfuse span を開始し、呼び出し元へコンテキストを提供する。"""

    try:
        langfuse = get_langfuse()
        if langfuse is None:
            yield None
            return
        trace_factory = getattr(langfuse, "trace", None)
        trace = None if trace_factory is None else trace_factory(name="LLM call")
    except Exception as exc:
        logger.warning(
            "langfuse_trace_initialization_failed",
            error_type=type(exc).__name__,
        )
        yield None
        return
    with span(trace=trace, name=name, input=_prepare_span_input(model, prompt)) as current:
        yield current


def _update_span_output(span_obj: Any, content: str) -> None:
    """出力ログの更新を Langfuse span へ委譲する。"""

    try:
        if span_obj is None:
            return
        payload: dict[str, Any] = {
            "content_chars": len(content),
            "content_sha256": content_hash(content),
        }
        if getattr(settings, "langfuse_log_full_output", False):
            max_chars = int(getattr(settings, "langfuse_output_max_chars", 40000))
            payload["content"] = content[: max(0, max_chars)]
        if hasattr(span_obj, "update"):
            span_obj.update(output=payload)
        elif hasattr(span_obj, "set_attribute"):
            span_obj.set_attribute("output", str(payload))  # type: ignore[call-arg]
    except Exception:
        pass


class _OpenAILLM(_LLMBase):  # pragma: no cover - オンライン利用が前提
    """OpenAI Responses API を利用する LLM ラッパー。"""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        reasoning: Optional[dict] = None,
        text: Optional[dict] = None,
        allow_parameter_fallbacks: bool = True,
        sdk_max_retries: int = 0,
    ) -> None:
        if OpenAI is None:
            raise RuntimeError("openai package not installed")
        client_options: dict[str, Any] = {
            "api_key": api_key,
            # 物理試行を来歴へ反映できる policy wrapper だけに再試行を集約する。
            "max_retries": max(0, sdk_max_retries),
        }
        self._client = OpenAI(**client_options)
        self._model = ensure_supported_llm_model(model)
        self._api_key = api_key
        self._reasoning = reasoning or {"effort": DEFAULT_REASONING_EFFORT}
        self._text = text or {"verbosity": DEFAULT_TEXT_VERBOSITY}
        self._allow_parameter_fallbacks = allow_parameter_fallbacks

    def _extract_text(self, resp: Any) -> str:
        """OpenAI Responses API のレスポンスから本文を抜き出す。"""

        try:
            txt = getattr(resp, "output_text", None)
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
        except Exception:
            pass
        try:
            choices = getattr(resp, "choices", None)
            if isinstance(choices, list) and choices:
                message = getattr(choices[0], "message", None)
                content = getattr(message, "content", None)
                if isinstance(content, str) and content.strip():
                    return content.strip()
        except Exception:
            pass
        try:
            data = resp if isinstance(resp, dict) else resp.model_dump()  # type: ignore[attr-defined]
            output = data.get("output") or []
            if output and isinstance(output, list):
                first = output[0] or {}
                contents = first.get("content") or []
                if contents and isinstance(contents, list):
                    text = contents[0].get("text")
                    if isinstance(text, str):
                        return text.strip()
        except Exception:
            pass
        return (str(resp) or "").strip()

    def _create_response(
        self,
        *,
        prompt: str,
        use_json: bool,
        include_reasoning: bool,
        include_text_options: bool,
    ) -> tuple[Any, dict[str, Any]]:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "input": prompt,
            "max_output_tokens": int(getattr(settings, "llm_max_tokens", 25000)),
            "timeout": settings.llm_timeout_ms / 1000.0,
            "store": False,
        }
        if include_reasoning and self._reasoning:
            kwargs["reasoning"] = self._reasoning
        text_options: dict[str, Any] = {}
        if include_text_options and isinstance(self._text, dict):
            text_options = dict(self._text)
        if use_json:
            text_options["format"] = {"type": "json_object"}
        if text_options:
            kwargs["text"] = text_options
        return self._client.responses.create(**kwargs), kwargs

    @staticmethod
    def _is_param_unsupported_error(exc: Exception) -> bool:
        text = (str(exc) or "").lower()
        error_type = type(exc).__name__.lower()
        return (
            "unsupported parameter" in text
            or "unknown parameter" in text
            or "unrecognized parameter" in text
            or "invalid parameter" in text
            or "not supported" in text
            or "unexpected keyword argument" in text
            or "got an unexpected keyword argument" in text
            or "unsupported" in error_type
        )

    @staticmethod
    def _response_attempts() -> list[dict[str, Any]]:
        return [
            {
                "use_json": True,
                "include_reasoning": True,
                "include_text_options": True,
                "label": "json_with_controls",
            },
            {
                "use_json": True,
                "include_reasoning": False,
                "include_text_options": False,
                "label": "json_without_optional_controls",
            },
            {
                "use_json": False,
                "include_reasoning": False,
                "include_text_options": False,
                "label": "plain_without_optional_controls",
            },
        ]

    @staticmethod
    def _plain_response_attempts() -> list[dict[str, Any]]:
        return [
            {
                "use_json": False,
                "include_reasoning": True,
                "include_text_options": True,
                "label": "plain_with_controls",
            },
            {
                "use_json": False,
                "include_reasoning": False,
                "include_text_options": False,
                "label": "plain_without_optional_controls",
            },
        ]

    @staticmethod
    def _get_value(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    @classmethod
    def _extract_usage(cls, resp: Any) -> TokenUsage:
        usage = cls._get_value(resp, "usage")
        input_details = cls._get_value(usage, "input_tokens_details", {})
        output_details = cls._get_value(usage, "output_tokens_details", {})

        def _int(value: Any) -> int | None:
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None

        return TokenUsage(
            input_tokens=_int(cls._get_value(usage, "input_tokens")),
            cached_input_tokens=_int(cls._get_value(input_details, "cached_tokens")),
            output_tokens=_int(cls._get_value(usage, "output_tokens")),
            reasoning_tokens=_int(cls._get_value(output_details, "reasoning_tokens")),
            total_tokens=_int(cls._get_value(usage, "total_tokens")),
        )

    def _complete_result_with_attempts(
        self,
        prompt: str,
        attempts: list[dict[str, Any]],
        response_mode: str,
        *,
        identity: PromptIdentity,
    ) -> CompletionResult:
        started = time.perf_counter()
        logger.info(
            "llm_complete_call",
            provider="openai",
            model=self._model,
            prompt_chars=len(prompt),
            response_mode=response_mode,
        )
        if self._api_key == "test-key":
            if response_mode == "plain":
                out = "テスト用のプレーンテキスト応答"
            else:
                out = '{"senses": [{"id": "s1", "gloss_ja": "テスト用の語義", "patterns": ["test pattern"]}], "sense_title": "テスト語義", "collocations": {"general": {"verb_object": ["test verb"], "adj_noun": ["test adj"], "prep_noun": ["test prep"]}, "academic": {"verb_object": [], "adj_noun": [], "prep_noun": []}}, "contrast": [], "examples": {"Dev": [{"en": "This is a test in dev.", "ja": "これは開発現場のテストです。"}], "CS": [], "LLM": [], "Business": [], "Common": []}, "etymology": {"note": "Test etymology", "confidence": "medium"}, "study_card": "テスト用の学習カード", "pronunciation": {"ipa_RP": "/test/"}}'
            logger.info(
                "llm_complete_result",
                provider="openai",
                model=self._model,
                content_chars=len(out),
                response_mode=response_mode,
            )
            return CompletionResult(
                content=out,
                provider="openai",
                requested_model=self._model,
                resolved_model=self._model,
                requested_parameters={
                    **dict(identity.requested_parameters),
                    "reasoning": self._reasoning,
                    "text": self._text,
                    "max_output_tokens": int(getattr(settings, "llm_max_tokens", 25000)),
                    "store": False,
                },
                effective_parameters={
                    **dict(identity.requested_parameters),
                    "response_mode": response_mode,
                    "profile": "test_key",
                },
                response_status="completed",
                latency_ms=int((time.perf_counter() - started) * 1000),
                prompt=identity,
                input_hash=content_hash(prompt),
                output_hash=content_hash(out),
                **runtime_correlation(),
            )

        last_exc: Exception | None = None
        failed_profiles: list[str] = []
        with _langfuse_span("openai.responses.create", self._model, prompt) as current_span:
            for attempt_index, attempt in enumerate(attempts):
                try:
                    attempt_observer = _PROVIDER_ATTEMPT_OBSERVER.get()
                    if attempt_observer is not None:
                        attempt_observer(attempt_index + 1)
                    resp, request_parameters = self._create_response(
                        prompt=prompt,
                        use_json=bool(attempt["use_json"]),
                        include_reasoning=bool(attempt["include_reasoning"]),
                        include_text_options=bool(attempt["include_text_options"]),
                    )
                    content = self._extract_text(resp)
                    logger.info(
                        "llm_complete_observed",
                        provider="openai",
                        model=self._model,
                        content_chars=len(content or ""),
                        content_sha256=content_hash(content or ""),
                        json_forced=bool(attempt["use_json"]),
                        param_profile=str(attempt["label"]),
                        response_mode=response_mode,
                        operation=identity.operation,
                    )
                    _update_span_output(current_span, content)
                    logger.info(
                        "llm_complete_result",
                        provider="openai",
                        model=self._model,
                        content_chars=len(content),
                        json_forced=bool(attempt["use_json"]),
                        param_profile=str(attempt["label"]),
                        response_mode=response_mode,
                    )
                    effective_parameters = {
                        "reasoning": request_parameters.get("reasoning"),
                        "text": request_parameters.get("text"),
                        "json_forced": bool(attempt["use_json"]),
                        "max_output_tokens": request_parameters["max_output_tokens"],
                        "store": request_parameters["store"],
                        "profile": str(attempt["label"]),
                    }
                    incomplete = self._get_value(resp, "incomplete_details")
                    correlation = runtime_correlation()
                    result = CompletionResult(
                        content=content,
                        provider="openai",
                        requested_model=self._model,
                        resolved_model=str(self._get_value(resp, "model") or self._model),
                        requested_parameters={
                            **dict(identity.requested_parameters),
                            "reasoning": self._reasoning,
                            "text": self._text,
                            "max_output_tokens": int(getattr(settings, "llm_max_tokens", 25000)),
                            "store": False,
                        },
                        effective_parameters=effective_parameters,
                        fallback_profile=(str(attempt["label"]) if failed_profiles else None),
                        fallback_reason=("PARAM_UNSUPPORTED" if failed_profiles else None),
                        failed_profiles=tuple(failed_profiles),
                        response_id=str(self._get_value(resp, "id") or "") or None,
                        response_status=str(self._get_value(resp, "status") or "") or None,
                        usage=self._extract_usage(resp),
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        attempt_count=attempt_index + 1,
                        finish_info=str(self._get_value(resp, "status") or "") or None,
                        incomplete_info=(str(incomplete)[:512] if incomplete else None),
                        prompt=identity,
                        input_hash=content_hash(prompt),
                        output_hash=content_hash(content),
                        **correlation,
                    )
                    return result
                except Exception as exc:
                    last_exc = exc
                    try:
                        setattr(exc, "llm_attempt_count", attempt_index + 1)
                    except Exception:
                        # Attribute-less exception types are counted as one attempt by the policy wrapper.
                        pass
                    if (
                        self._is_param_unsupported_error(exc)
                        and attempt_index < len(attempts) - 1
                    ):
                        failed_profiles.append(str(attempt["label"]))
                        logger.info(
                            "llm_complete_param_fallback",
                            provider="openai",
                            model=self._model,
                            failed_profile=str(attempt["label"]),
                            next_profile=str(attempts[attempt_index + 1]["label"]),
                            error_type=type(exc).__name__,
                            error=str(exc)[:256],
                            response_mode=response_mode,
                            operation=identity.operation,
                            attempt=attempt_index + 1,
                            reason_code="PARAM_UNSUPPORTED",
                        )
                        continue
                    raise
        raise last_exc if last_exc else RuntimeError("LLM call failed with unsupported params")

    def complete(self, prompt: str) -> str:
        identity = PromptIdentity(
            "legacy.complete", "legacy", "legacy", "legacy.complete", {}
        )
        return self.complete_result(prompt, identity=identity, response_mode="json").content

    def complete_text(self, prompt: str) -> str:
        identity = PromptIdentity(
            "legacy.complete_text", "legacy", "text", "legacy.complete_text", {}
        )
        return self.complete_result(prompt, identity=identity, response_mode="plain").content

    def complete_result(
        self,
        prompt: str,
        *,
        identity: PromptIdentity,
        response_mode: str = "json",
    ) -> CompletionResult:
        attempts = (
            self._plain_response_attempts()
            if response_mode == "plain"
            else self._response_attempts()
        )
        if not self._allow_parameter_fallbacks:
            attempts = attempts[:1]
        return self._complete_result_with_attempts(
            prompt, attempts, response_mode=response_mode, identity=identity
        )


def _llm_with_policy(llm: _LLMBase, *, max_attempts: int | None = None) -> _LLMBase:
    """タイムアウトとリトライを付与した LLM ラッパーを返す。"""

    executor = _get_llm_executor()

    class _Wrapped(_LLMBase):
        def complete(self, prompt: str) -> str:
            return self._run_with_policy("complete", prompt)

        def complete_text(self, prompt: str) -> str:
            return self._run_with_policy("complete_text", prompt)

        def complete_result(
            self,
            prompt: str,
            *,
            identity: PromptIdentity,
            response_mode: str = "json",
        ) -> CompletionResult:
            return self._run_result_with_policy(
                prompt, identity=identity, response_mode=response_mode
            )

        def _run_result_with_policy(
            self,
            prompt: str,
            *,
            identity: PromptIdentity,
            response_mode: str,
        ) -> CompletionResult:
            last_exc: Exception | None = None
            completed_attempts = 0
            attempt_limit = max_attempts or max(1, settings.llm_max_retries)
            for policy_attempt in range(1, attempt_limit + 1):
                future = None
                provider_attempts = {"count": 0}
                try:
                    ctx = contextvars.copy_context()

                    def invoke_provider() -> CompletionResult:
                        def observe_attempt(count: int) -> None:
                            provider_attempts["count"] = max(
                                provider_attempts["count"], count
                            )

                        token = _PROVIDER_ATTEMPT_OBSERVER.set(observe_attempt)
                        try:
                            return llm.complete_result(
                                prompt,
                                identity=identity,
                                response_mode=response_mode,
                            )
                        finally:
                            _PROVIDER_ATTEMPT_OBSERVER.reset(token)

                    future = executor.submit(
                        ctx.run,
                        invoke_provider,
                    )
                    result = future.result(timeout=settings.llm_timeout_ms / 1000.0)
                    return replace(
                        result,
                        attempt_count=completed_attempts + max(1, result.attempt_count),
                    )
                except Exception as exc:
                    last_exc = exc
                    completed_attempts += max(
                        1,
                        provider_attempts["count"],
                        int(getattr(exc, "llm_attempt_count", 1)),
                    )
                    logger.info(
                        "llm_complete_error",
                        attempt=policy_attempt,
                        retries=settings.llm_max_retries,
                        error_type=type(exc).__name__,
                        method="complete_result",
                        operation=identity.operation,
                    )
                    if future is not None:
                        future.cancel()
                    if policy_attempt >= attempt_limit:
                        break
                    time.sleep(0.1 * policy_attempt)
            if settings.strict_mode:
                raise RuntimeError("LLM typed completion failed") from last_exc
            content = ""
            return CompletionResult(
                content=content,
                provider="fallback",
                requested_model=str(identity.requested_parameters.get("model") or "") or None,
                resolved_model=None,
                requested_parameters=dict(identity.requested_parameters),
                effective_parameters={},
                fallback_reason="PROVIDER_FAILURE",
                attempt_count=max(1, completed_attempts),
                prompt=identity,
                input_hash=content_hash(prompt),
                output_hash=content_hash(content),
                **runtime_correlation(),
            )

        def _run_with_policy(self, method_name: str, prompt: str) -> str:
            last_exc: Exception | None = None
            attempt_limit = max_attempts or max(1, settings.llm_max_retries)
            for attempt in range(1, attempt_limit + 1):
                future = None
                try:
                    ctx = contextvars.copy_context()
                    method = getattr(llm, method_name)
                    future = executor.submit(ctx.run, method, prompt)
                    result = future.result(timeout=settings.llm_timeout_ms / 1000.0)
                    if result == "":
                        logger.info(
                            "llm_complete_empty",
                            attempt=attempt,
                            retries=settings.llm_max_retries,
                            method=method_name,
                        )
                    return result
                except Exception as exc:
                    last_exc = exc
                    logger.info(
                        "llm_complete_error",
                        attempt=attempt,
                        retries=settings.llm_max_retries,
                        error_type=type(exc).__name__,
                        error=str(exc),
                        method=method_name,
                    )
                    if future is not None:
                        try:
                            future.cancel()
                        except Exception:
                            pass
                    if attempt >= attempt_limit:
                        break
                    time.sleep(0.1 * attempt)
            logger.info(
                "llm_complete_failed_all_retries",
                error=str(last_exc) if last_exc else None,
                error_type=(type(last_exc).__name__ if last_exc else None),
                method=method_name,
            )
            if settings.strict_mode:
                reason_code = "UNKNOWN"
                base_msg = "LLM failure"
                text = (str(last_exc) or "") if last_exc else ""
                etype = type(last_exc).__name__ if last_exc else "None"
                low = text.lower()
                if isinstance(last_exc, FuturesTimeout) or "timeout" in low:
                    base_msg = "LLM timeout"
                    reason_code = "TIMEOUT"
                elif (
                    "rate limit" in low
                    or "too many requests" in low
                    or "429" in low
                    or "ratelimit" in etype.lower()
                ):
                    reason_code = "RATE_LIMIT"
                elif (
                    "auth" in low
                    or "invalid api key" in low
                    or "unauthorized" in low
                    or "401" in low
                ):
                    reason_code = "AUTH"
                elif "unsupported parameter" in low or "not supported" in low:
                    reason_code = "PARAM_UNSUPPORTED"
                elif (
                    "unexpected keyword argument" in low
                    or "got an unexpected keyword argument" in low
                ):
                    reason_code = "PARAM_UNSUPPORTED"
                msg = (
                    f"{base_msg} (reason_code={reason_code}, error_type={etype}, detail={text[:256]})"
                )
                raise RuntimeError(msg)
            return ""

    return _Wrapped()


def get_llm_provider(
    *,
    model_override: str | None = None,
    reasoning_override: Optional[dict] = None,
    text_override: Optional[dict] = None,
    single_attempt: bool = False,
) -> Any:
    """設定値に応じた LLM クライアントを返す。"""

    has_override = any(
        value is not None
        for value in (model_override, reasoning_override, text_override)
    ) or single_attempt
    instance = _get_llm_instance()
    if not has_override and instance is not None:
        return instance

    provider = (settings.llm_provider or "").lower()
    try:
        if provider in {"", "local"}:
            if settings.strict_mode:
                raise RuntimeError("LLM_PROVIDER must be 'openai' in strict mode")
            logger.info("llm_provider_select", provider="local")
            wrapped = _llm_with_policy(_LocalEchoLLM())
            if not has_override:
                _set_llm_instance(wrapped)
            return wrapped

        if provider == "openai":
            api_key = settings.openai_api_key
            if not api_key:
                if settings.strict_mode:
                    raise RuntimeError(
                        "OPENAI_API_KEY is required for LLM_PROVIDER=openai (strict mode)"
                    )
                logger.info("llm_provider_select", provider="local", reason="missing_api_key")
                fallback = _llm_with_policy(_LocalEchoLLM())
                if not has_override:
                    _set_llm_instance(fallback)
                return fallback

            base_model = getattr(settings, "llm_model", None)
            base_reasoning = getattr(settings, "llm_reasoning", None)
            base_text_opts = getattr(settings, "llm_text_options", None)
            llm = _OpenAILLM(
                api_key=api_key,
                model=model_override or base_model,
                reasoning=(
                    reasoning_override
                    if reasoning_override is not None
                    else base_reasoning
                ),
                text=text_override if text_override is not None else base_text_opts,
                allow_parameter_fallbacks=not single_attempt,
                sdk_max_retries=0,
            )
            wrapped = _llm_with_policy(llm, max_attempts=1 if single_attempt else None)
            if not has_override:
                _set_llm_instance(wrapped)
            return wrapped

        if settings.strict_mode:
            raise RuntimeError(f"Unknown LLM provider: {provider}")
        logger.info(
            "llm_provider_select",
            provider="local",
            reason="unknown_provider",
            requested=provider,
        )
        fallback = _llm_with_policy(_LocalEchoLLM())
        if not has_override:
            _set_llm_instance(fallback)
        return fallback
    except Exception:
        if settings.strict_mode:
            raise
        logger.info("llm_provider_select", provider="local", reason="exception")
        fallback = _llm_with_policy(_LocalEchoLLM())
        if not has_override:
            _set_llm_instance(fallback)
        return fallback


def shutdown_providers() -> None:
    """共有スレッドプールと LLM シングルトンを解放する。"""

    executor = _get_llm_executor()
    try:
        executor.shutdown(wait=False, cancel_futures=True)  # type: ignore[call-arg]
    except Exception:
        pass
    _set_llm_instance(None)
