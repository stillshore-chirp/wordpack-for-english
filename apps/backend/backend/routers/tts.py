from __future__ import annotations

import os
import threading
import time
from typing import Any, Iterator

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError, constr

from ..config import settings
from ..authorization.dependencies import require_user_permission
from ..authorization.permissions import Permission
from ..authorization.principal import Principal
from ..logging import logger

try:
    from openai import (  # type: ignore
        APIConnectionError,
        APIError,
        APIStatusError,
        AuthenticationError,
        BadRequestError,
        OpenAI,
        RateLimitError,
    )
except Exception:  # pragma: no cover - openai SDK が無い環境では初期化しない
    APIConnectionError = APIError = APIStatusError = AuthenticationError = (
        BadRequestError
    ) = RateLimitError = None  # type: ignore[assignment]
    OpenAI = None  # type: ignore[assignment]


# TTS 入力文字数の上限。フロントエンド (apps/frontend/src/constants/tts.ts) と同期する。
TTS_TEXT_MAX_LENGTH = 500

router = APIRouter(prefix="/api/tts", tags=["tts"])

_CLIENT_LOCK = threading.Lock()


def _init_client() -> OpenAI | None:  # type: ignore[valid-type]
    """Instantiate an OpenAI client when SDK and API key are available."""
    if OpenAI is None:  # pragma: no cover - SDK 未導入環境
        return None
    api_key = settings.openai_api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def _iter_audio_bytes(response: object) -> Iterator[bytes]:
    """Iterate over MP3 bytes from OpenAI streaming responses."""
    if hasattr(response, "iter_bytes"):
        yield from response.iter_bytes()  # type: ignore[misc]
    else:  # pragma: no cover - 想定外フォーマット
        raise RuntimeError("streaming response does not provide iter_bytes")


client = _init_client()


class TTSIn(BaseModel):
    text: constr(min_length=1, max_length=TTS_TEXT_MAX_LENGTH)
    voice: str = "alloy"


def _build_text_too_long_error() -> dict[str, Any]:
    """TTS 入力テキスト超過時に返却するエラー本文を標準化する。"""

    return {
        "error": "tts_text_too_long",
        "message": (
            "読み上げテキストは"
            f"{TTS_TEXT_MAX_LENGTH}文字以内で入力してください。"
        ),
        "max_length": TTS_TEXT_MAX_LENGTH,
    }


def _validate_tts_request(payload: dict[str, Any]) -> TTSIn:
    """TTS リクエストを検証し、文字数超過だけは 413 へ変換する。"""

    try:
        return TTSIn.model_validate(payload)
    except ValidationError as exc:
        for err in exc.errors():
            if err.get("type") == "string_too_long" and tuple(err.get("loc", ())) == ("text",):
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=_build_text_too_long_error(),
                ) from exc
        raise RequestValidationError(exc.errors()) from exc


def _tts_client() -> OpenAI | None:  # type: ignore[valid-type]
    global client
    if client is not None:
        return client
    with _CLIENT_LOCK:
        if client is None:
            client = _init_client()
    return client


def _text_preview(text: str, limit: int = 80) -> str:
    sanitized = " ".join(text.strip().split())
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 1] + "…"


def _loggable_request_id(request: Request | None) -> str | None:
    if request is None:
        return None
    return getattr(request.state, "request_id", None)


def _map_openai_exception(exc: Exception) -> tuple[int, str, str]:
    if AuthenticationError is not None and isinstance(exc, AuthenticationError):
        return 502, "OpenAI authentication failed", "authentication_error"
    if RateLimitError is not None and isinstance(exc, RateLimitError):
        return 429, "OpenAI rate limit exceeded", "rate_limit"
    if BadRequestError is not None and isinstance(exc, BadRequestError):
        return 400, "Invalid text-to-speech request", "bad_request"
    if APIConnectionError is not None and isinstance(exc, APIConnectionError):
        return 502, "OpenAI connection error", "connection_error"
    if APIStatusError is not None and isinstance(exc, APIStatusError):
        return (
            exc.status_code or 502,
            "OpenAI returned an error response",
            "api_status_error",
        )
    if APIError is not None and isinstance(exc, APIError):
        return 502, "OpenAI API error", "api_error"
    return 500, "Text-to-speech failed", "unexpected_error"


@router.post("", response_class=StreamingResponse)
def synth(
    request: Request,
    payload: dict[str, Any] = Body(...),
    _principal: Principal = Depends(require_user_permission(Permission.TTS_CREATE)),
) -> StreamingResponse:
    """Synthesize speech using OpenAI TTS and stream MP3 audio to the client."""
    t0 = time.perf_counter()
    request_id = _loggable_request_id(request)
    raw_text = payload.get("text") if isinstance(payload, dict) else None
    raw_text_chars = len(raw_text) if isinstance(raw_text, str) else 0

    try:
        req = _validate_tts_request(payload)
    except HTTPException as exc:
        logger.warning(
            "tts_request_rejected",
            request_id=request_id,
            reason="text_too_long",
            text_chars=raw_text_chars,
            max_length=TTS_TEXT_MAX_LENGTH,
        )
        raise exc

    text_chars = len(req.text)
    logger.info(
        "tts_request",
        request_id=request_id,
        voice=req.voice,
        text_chars=text_chars,
        text_preview=_text_preview(req.text),
    )

    client_instance = _tts_client()
    if client_instance is None:
        logger.error(
            "tts_client_unavailable",
            request_id=request_id,
            reason="missing_sdk_or_api_key",
        )
        raise HTTPException(status_code=500, detail="OpenAI client is not configured")

    response_ctx: object | None = None
    response_obj: object | None = None
    use_streaming_api = False

    try:
        streaming_api = getattr(
            getattr(client_instance.audio, "speech", None),
            "with_streaming_response",
            None,
        )
        if streaming_api is not None and hasattr(streaming_api, "create"):
            use_streaming_api = True
            response_ctx = streaming_api.create(
                model="gpt-4o-mini-tts",
                voice=req.voice,
                input=req.text,
                response_format="mp3",
            )
        else:
            response_obj = client_instance.audio.speech.create(  # type: ignore[union-attr]
                model="gpt-4o-mini-tts",
                voice=req.voice,
                input=req.text,
                response_format="mp3",
            )
    except Exception as exc:  # pragma: no cover - SDK からの例外を分類
        status_code, detail, reason = _map_openai_exception(exc)
        logger.warning(
            "tts_request_failed",
            request_id=request_id,
            voice=req.voice,
            text_chars=text_chars,
            reason=reason,
            error=str(exc),
        )
        raise HTTPException(status_code=status_code, detail=detail) from exc

    def stream() -> Iterator[bytes]:
        nonlocal response_obj
        total_bytes = 0
        had_error = False
        try:
            if use_streaming_api and response_ctx is not None:
                with response_ctx as response:
                    response_obj = response
                    for chunk in _iter_audio_bytes(response):
                        total_bytes += len(chunk)
                        yield chunk
            elif response_obj is not None:
                for chunk in _iter_audio_bytes(response_obj):
                    total_bytes += len(chunk)
                    yield chunk
            else:  # pragma: no cover - 想定外フォーマット
                raise RuntimeError("text-to-speech response missing audio bytes")
        except Exception as exc:  # pragma: no cover - ストリーミング中の異常
            had_error = True
            logger.error(
                "tts_stream_error",
                request_id=request_id,
                voice=req.voice,
                text_chars=text_chars,
                streamed_bytes=total_bytes,
                error=str(exc),
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000
            try:
                close_target = response_ctx if use_streaming_api else response_obj
                if close_target is not None and hasattr(close_target, "close"):
                    close_target.close()  # type: ignore[misc]
            except Exception:  # pragma: no cover - close に失敗しても継続
                logger.warning(
                    "tts_stream_close_failed",
                    request_id=request_id,
                    voice=req.voice,
                    streamed_bytes=total_bytes,
                )
            if not had_error:
                logger.info(
                    "tts_stream_complete",
                    request_id=request_id,
                    voice=req.voice,
                    text_chars=text_chars,
                    streamed_bytes=total_bytes,
                    duration_ms=duration_ms,
                )

    return StreamingResponse(stream(), media_type="audio/mpeg")
