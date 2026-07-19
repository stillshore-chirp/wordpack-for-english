from __future__ import annotations

import time
from contextlib import contextmanager, nullcontext
from typing import Any, ContextManager

from ..config import settings
from ..logging import logger

try:  # pragma: no cover - optional dependency in tests
    from langfuse import Langfuse
except Exception:  # pragma: no cover
    Langfuse = None  # type: ignore

try:  # optional in tests; required for v4 trace attributes
    from langfuse import propagate_attributes
except Exception:  # pragma: no cover
    propagate_attributes = None  # type: ignore


_langfuse_client: Any | None = None


def is_langfuse_enabled() -> bool:
    if not getattr(settings, "langfuse_enabled", False):
        return False
    if Langfuse is None:
        if settings.strict_mode:
            raise RuntimeError(
                "langfuse package is required when LANGFUSE_ENABLED=true (strict mode)"
            )
        return False
    if not (
        settings.langfuse_public_key
        and settings.langfuse_secret_key
        and settings.langfuse_host
    ):
        if settings.strict_mode:
            raise RuntimeError(
                "LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST are required when LANGFUSE_ENABLED=true (strict mode)"
            )
        return False
    return True


def get_langfuse() -> Any | None:
    global _langfuse_client
    if _langfuse_client is not None:
        return _langfuse_client
    if not is_langfuse_enabled():
        return None
    try:
        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,  # type: ignore[arg-type]
            secret_key=settings.langfuse_secret_key,  # type: ignore[arg-type]
            host=settings.langfuse_host,  # type: ignore[arg-type]
            release=settings.langfuse_release,
        )
        return _langfuse_client
    except Exception as exc:  # pragma: no cover - init happens once
        if settings.strict_mode:
            raise
        logger.warning("langfuse_init_failed", error=repr(exc))
        return None


@contextmanager
def request_trace(
    *,
    name: str,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    path: str | None = None,
) -> ContextManager[dict[str, Any]]:
    # 一部のルート（例: /healthz）は観測対象から除外してノイズを減らす
    try:
        exclude = getattr(settings, "langfuse_exclude_paths", [])
        p = path or (metadata or {}).get("path") if isinstance(metadata, dict) else None
        if p and isinstance(exclude, list):
            for pat in exclude:
                try:
                    if not isinstance(pat, str):
                        continue
                    if pat.endswith("*"):
                        if p.startswith(pat[:-1]):
                            yield {"trace": None}
                            return
                    elif p == pat:
                        yield {"trace": None}
                        return
                except Exception:
                    pass
    except Exception:
        # 例外時は除外せず通常通りに進める
        pass

    lf = get_langfuse()
    start = time.time()
    # --- v4: observation API と OpenTelemetry context propagation ---
    if lf is not None and hasattr(lf, "start_as_current_observation"):
        try:
            attributes_cm = (
                propagate_attributes(
                    user_id=user_id,
                    metadata=metadata or None,
                    trace_name=name,
                )
                if propagate_attributes is not None
                else nullcontext()
            )
        except Exception as exc:
            logger.warning("langfuse_trace_attributes_failed", error=repr(exc))
            if settings.strict_mode:
                raise
            attributes_cm = nullcontext()
        try:
            observation_cm = lf.start_as_current_observation(
                name=name,
                as_type="span",
                metadata=metadata or None,
            )
        except Exception as exc:
            logger.warning("langfuse_trace_create_failed", error=repr(exc))
            if settings.strict_mode:
                raise
            observation_cm = None
        if observation_cm is not None:
            with attributes_cm:
                with observation_cm as parent_span:
                    ctx = {"trace": parent_span}
                    final_metadata = dict(metadata or {})
                    try:
                        yield ctx
                    except Exception as exc:
                        final_metadata["error"] = str(exc)[:500]
                        try:
                            parent_span.update(
                                level="ERROR",
                                status_message=str(exc)[:500],
                            )
                        except Exception:
                            pass
                        raise
                    finally:
                        final_metadata["duration_ms"] = (
                            time.time() - start
                        ) * 1000.0
                        try:
                            parent_span.update(metadata=final_metadata)
                        except Exception:
                            pass
            return
    # --- v3: context manager でスパンを開始し、その内側で処理を実行する ---
    if lf is not None and (
        hasattr(lf, "start_as_current_span") or hasattr(lf, "start_span")
    ):
        try:
            cm = (
                lf.start_as_current_span(name=name)
                if hasattr(lf, "start_as_current_span")
                else lf.start_span(name=name)
            )  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover
            logger.warning("langfuse_trace_create_failed", error=repr(exc))
            cm = None
        if cm is not None:
            try:
                with cm as parent_span:  # v3 は with で開始/終了
                    if user_id and hasattr(parent_span, "set_attribute"):
                        parent_span.set_attribute("user_id", user_id)  # type: ignore[call-arg]
                    if metadata and hasattr(parent_span, "set_attribute"):
                        # フラット属性として付与
                        for k, v in (metadata or {}).items():
                            try:
                                parent_span.set_attribute(str(k), v)  # type: ignore[call-arg]
                            except Exception:
                                pass
                    ctx = {"trace": parent_span}
                    try:
                        yield ctx
                    except Exception as exc:
                        if hasattr(parent_span, "set_attribute"):
                            parent_span.set_attribute("error", str(exc)[:500])  # type: ignore[call-arg]
                        raise
                    finally:
                        if hasattr(parent_span, "set_attribute"):
                            duration_ms = (time.time() - start) * 1000.0
                            parent_span.set_attribute("duration_ms", duration_ms)  # type: ignore[call-arg]
            finally:
                # with により自動終了
                pass
            return
    # --- v2: 従来 API ---
    trace: Any | None = None
    if lf is not None:
        try:
            if hasattr(lf, "trace"):
                trace = lf.trace(
                    name=name,
                    user_id=user_id,
                    metadata=metadata or {},
                )
            elif hasattr(lf, "create_trace"):
                trace = lf.create_trace(  # type: ignore[attr-defined]
                    name=name,
                    user_id=user_id,
                    metadata=metadata or {},
                )
            else:
                logger.warning(
                    "langfuse_trace_api_missing",
                    error="no trace/create_trace on client",
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("langfuse_trace_create_failed", error=repr(exc))
    ctx = {"trace": trace}
    try:
        yield ctx
    except Exception as exc:
        if trace is not None:
            try:
                trace.update(
                    input=None, output=None, metadata={"error": str(exc)[:500]}
                )
                trace.end()
            except Exception:
                pass
        raise
    finally:
        if trace is not None:
            try:
                duration_ms = (time.time() - start) * 1000.0
                trace.update(metadata={(metadata or {}) | {"duration_ms": duration_ms}})
                trace.end()
            except Exception:
                pass


@contextmanager
def span(
    *,
    trace: Any | None,
    name: str,
    input: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContextManager[Any | None]:
    lf = get_langfuse()
    start = time.time()
    # v4: current observation の内側に子 observation を開始
    if lf is not None and hasattr(lf, "start_as_current_observation"):
        try:
            cm = lf.start_as_current_observation(
                name=name,
                as_type="span",
                input=str(input)[:40000] if input is not None else None,
                metadata=metadata or None,
            )
        except Exception as exc:  # pragma: no cover
            logger.warning("langfuse_span_create_failed", error=repr(exc))
            cm = None
        if cm is None:
            yield None
            return
        try:
            with cm as s:
                final_metadata = dict(metadata or {})
                try:
                    yield s
                except Exception as exc:
                    final_metadata["error"] = str(exc)[:500]
                    try:
                        s.update(
                            level="ERROR",
                            status_message=str(exc)[:500],
                        )
                    except Exception:
                        pass
                    raise
                finally:
                    final_metadata["duration_ms"] = (
                        time.time() - start
                    ) * 1000.0
                    try:
                        s.update(metadata=final_metadata)
                    except Exception:
                        pass
        finally:
            pass
        return
    # v3: 親スパン（request_trace 内）直下に current span を開始
    if lf is not None and (
        hasattr(lf, "start_as_current_span") or hasattr(lf, "start_span")
    ):
        try:
            cm = (
                lf.start_as_current_span(name=name)
                if hasattr(lf, "start_as_current_span")
                else lf.start_span(name=name)
            )  # type: ignore[assignment]
        except Exception as exc:  # pragma: no cover
            logger.warning("langfuse_span_create_failed", error=repr(exc))
            cm = None
        if cm is None:
            yield None
            return
        try:
            with cm as s:
                # v3: 入力は update(input=...) を優先。未対応クライアントには属性でフォールバック。
                if input is not None:
                    try:
                        if hasattr(s, "update"):
                            s.update(input=str(input)[:40000])  # type: ignore[call-arg]
                        elif hasattr(s, "set_attribute"):
                            s.set_attribute("input", str(input)[:40000])  # type: ignore[call-arg]
                    except Exception:
                        pass
                if metadata and hasattr(s, "set_attribute"):
                    for k, v in (metadata or {}).items():
                        try:
                            s.set_attribute(str(k), v)  # type: ignore[call-arg]
                        except Exception:
                            pass
                try:
                    yield s
                except Exception as exc:
                    if hasattr(s, "update"):
                        try:
                            s.update(metadata={"error": str(exc)[:500]})  # type: ignore[call-arg]
                        except Exception:
                            pass
                    elif hasattr(s, "set_attribute"):
                        s.set_attribute("error", str(exc)[:500])  # type: ignore[call-arg]
                    raise
                finally:
                    duration_ms = (time.time() - start) * 1000.0
                    try:
                        if hasattr(s, "update"):
                            s.update(metadata={"duration_ms": duration_ms})  # type: ignore[call-arg]
                        elif hasattr(s, "set_attribute"):
                            s.set_attribute("duration_ms", duration_ms)  # type: ignore[call-arg]
                    except Exception:
                        pass
        finally:
            pass
        return
    # v2: 旧 API
    if lf is None or trace is None:
        yield None
        return
    s: Any | None = None
    try:
        if hasattr(trace, "span"):
            s = trace.span(name=name, input=input, metadata=metadata or {})
        elif hasattr(trace, "create_span"):
            s = trace.create_span(name=name, input=input, metadata=metadata or {})  # type: ignore[attr-defined]
    except Exception as exc:  # pragma: no cover
        logger.warning("langfuse_span_create_failed", error=repr(exc))
    try:
        yield s
    except Exception as exc:
        if s is not None:
            try:
                s.update(
                    output=None, metadata={(metadata or {}) | {"error": str(exc)[:500]}}
                )
                s.end()
            except Exception:
                pass
        raise
    finally:
        if s is not None:
            try:
                duration_ms = (time.time() - start) * 1000.0
                s.update(metadata={(metadata or {}) | {"duration_ms": duration_ms}})
                s.end()
            except Exception:
                pass
