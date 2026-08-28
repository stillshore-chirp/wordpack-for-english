from __future__ import annotations

import asyncio
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from ...domain.quiz.generation_progress import (
    QUIZ_GENERATION_ATTEMPT_LIMIT,
    QuizGenerationPhase,
    QuizGenerationProgress,
    QuizGenerationProgressCallback,
)
from ...logging import logger
from ...llmops.completion import generation_workflow_context
from ...models.quiz import Quiz, QuizGenerateRequest, QuizGenerationJobResponse
from ..common.ports import Clock, IdGenerator, TaskScheduler


class QuizGenerator(Protocol):
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress: QuizGenerationProgressCallback | None = None,
    ) -> Quiz:
        raise NotImplementedError


@dataclass
class QuizGenerationJob:
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    quiz_id: str | None = None
    result: Quiz | None = None
    error: str | None = None
    error_code: str | None = None
    attempt_count: int = 0
    attempt_limit: int = QUIZ_GENERATION_ATTEMPT_LIMIT
    retry_phase: QuizGenerationPhase | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_response(self) -> QuizGenerationJobResponse:
        return QuizGenerationJobResponse(
            job_id=self.job_id,
            status=self.status,
            quiz_id=self.quiz_id,
            result=self.result,
            error=self.error,
            error_code=self.error_code,
            attempt_count=self.attempt_count,
            attempt_limit=self.attempt_limit,
            retry_phase=self.retry_phase,
        )


_quiz_generation_jobs: dict[str, QuizGenerationJob] = {}
_quiz_generation_lock = asyncio.Lock()


def _store_supports_persistent_jobs(store: object) -> bool:
    return all(
        callable(getattr(store, name, None))
        for name in (
            "create_quiz_generation_job",
            "update_quiz_generation_job",
            "get_quiz_generation_job",
        )
    )


def _record_int(value: object, *, default: int, minimum: int) -> int:
    try:
        return max(minimum, int(value))
    except (TypeError, ValueError):
        return default


def _job_from_record(record: Mapping[str, object], *, clock: Clock) -> QuizGenerationJob:
    status = str(record.get("status") or "queued")
    if status not in {"queued", "running", "succeeded", "failed"}:
        status = "failed"
    result = None
    if record.get("result_json") is not None:
        try:
            result = Quiz.model_validate_json(str(record.get("result_json")))
        except Exception as exc:  # pragma: no cover - defensive logging for corrupt data
            logger.error(
                "quiz_generation_result_parse_failed",
                job_id=str(record.get("job_id") or ""),
                error_type=exc.__class__.__name__,
                error_message=str(exc)[:200],
            )
    error = record.get("error")
    error_code = record.get("error_code")
    retry_phase_raw = str(record.get("retry_phase") or "")
    retry_phase = (
        retry_phase_raw
        if retry_phase_raw in {"generation", "json_repair", "translation_alignment"}
        else None
    )
    return QuizGenerationJob(
        job_id=str(record.get("job_id") or ""),
        status=status,  # type: ignore[arg-type]
        quiz_id=str(record.get("quiz_id") or "") or None,
        result=result,
        error=str(error) if error is not None else None,
        error_code=str(error_code) if error_code is not None else None,
        attempt_count=_record_int(
            record.get("attempt_count"),
            default=0,
            minimum=0,
        ),
        attempt_limit=_record_int(
            record.get("attempt_limit"),
            default=QUIZ_GENERATION_ATTEMPT_LIMIT,
            minimum=1,
        ),
        retry_phase=retry_phase,  # type: ignore[arg-type]
        created_at=str(record.get("created_at") or clock.now_iso()),
        updated_at=str(record.get("updated_at") or clock.now_iso()),
    )


def _create_job_record(store: object, job_id: str, *, clock: Clock) -> QuizGenerationJob:
    if _store_supports_persistent_jobs(store):
        record = store.create_quiz_generation_job(job_id=job_id, status="queued")
        return _job_from_record(record, clock=clock)
    now = clock.now_iso()
    return QuizGenerationJob(
        job_id=job_id,
        status="queued",
        attempt_limit=QUIZ_GENERATION_ATTEMPT_LIMIT,
        created_at=now,
        updated_at=now,
    )


def _update_job_record(
    store: object,
    job_id: str,
    *,
    status: Literal["queued", "running", "succeeded", "failed"],
    clock: Clock,
    quiz: Quiz | None = None,
    error: str | None = None,
    error_code: str | None = None,
    attempt_count: int | None = None,
    attempt_limit: int | None = None,
    retry_phase: QuizGenerationPhase | None = None,
) -> QuizGenerationJob | None:
    if _store_supports_persistent_jobs(store):
        record = store.update_quiz_generation_job(
            job_id,
            status=status,
            quiz_id=quiz.id if quiz is not None else None,
            result_json=quiz.model_dump_json() if quiz is not None else None,
            error=error,
            error_code=error_code,
            attempt_count=attempt_count,
            attempt_limit=attempt_limit,
            retry_phase=retry_phase,
        )
        return _job_from_record(record, clock=clock) if record is not None else None
    job = _quiz_generation_jobs.get(job_id)
    if job is None:
        return None
    job.status = status
    job.updated_at = clock.now_iso()
    if quiz is not None:
        job.quiz_id = quiz.id
        job.result = quiz
    if error is not None:
        job.error = error
    if error_code is not None:
        job.error_code = error_code
    if attempt_count is not None:
        job.attempt_count = attempt_count
    if attempt_limit is not None:
        job.attempt_limit = attempt_limit
    if retry_phase is not None:
        job.retry_phase = retry_phase
    _quiz_generation_jobs[job_id] = job
    return job


def _get_job_record(
    store: object,
    job_id: str,
    *,
    clock: Clock,
) -> QuizGenerationJob | None:
    if _store_supports_persistent_jobs(store):
        record = store.get_quiz_generation_job(job_id)
        if record is None:
            return None
        return _job_from_record(record, clock=clock)
    return _quiz_generation_jobs.get(job_id)


async def enqueue_quiz_generation_job(
    req: QuizGenerateRequest,
    store: object,
    *,
    generator: QuizGenerator,
    scheduler: TaskScheduler | None,
    id_generator: IdGenerator,
    clock: Clock,
) -> QuizGenerationJobResponse:
    job_id = id_generator.new_id()
    job = _create_job_record(store, job_id, clock=clock)
    async with _quiz_generation_lock:
        _quiz_generation_jobs[job_id] = job
    if scheduler is None:
        await _run_quiz_generation_job(
            job_id,
            req,
            store,
            generator=generator,
            clock=clock,
        )
    else:
        scheduler.spawn(
            _run_quiz_generation_job(
                job_id,
                req,
                store,
                generator=generator,
                clock=clock,
            )
        )
    return job.to_response()


async def get_quiz_generation_job(
    job_id: str,
    store: object,
    *,
    clock: Clock,
) -> QuizGenerationJobResponse | None:
    async with _quiz_generation_lock:
        job = _get_job_record(store, job_id, clock=clock)
        return job.to_response() if job else None


async def _run_quiz_generation_job(
    job_id: str,
    req: QuizGenerateRequest,
    store: object,
    *,
    generator: QuizGenerator,
    clock: Clock,
) -> None:
    async with _quiz_generation_lock:
        job = _update_job_record(store, job_id, status="running", clock=clock)
        if job is None:
            return
    loop = asyncio.get_running_loop()
    loop_thread_id = threading.get_ident()

    async def persist_progress(progress: QuizGenerationProgress) -> None:
        async with _quiz_generation_lock:
            _update_job_record(
                store,
                job_id,
                status="running",
                clock=clock,
                attempt_count=progress.attempt_count,
                attempt_limit=progress.attempt_limit,
                retry_phase=progress.retry_phase,
            )

    def report_progress(progress: QuizGenerationProgress) -> None:
        try:
            if threading.get_ident() == loop_thread_id:
                loop.create_task(persist_progress(progress))
                return
            future = asyncio.run_coroutine_threadsafe(persist_progress(progress), loop)
            future.result(timeout=15)
        except Exception as exc:  # pragma: no cover - persistence failure is non-fatal
            logger.warning(
                "quiz_generation_progress_update_failed",
                job_id=job_id,
                attempt_count=progress.attempt_count,
                attempt_limit=progress.attempt_limit,
                retry_phase=progress.retry_phase,
                error_type=type(exc).__name__,
            )

    try:
        with generation_workflow_context(job_id):
            quiz = await generator.generate(
                req,
                store,
                on_progress=report_progress,
            )
    except Exception as exc:
        raw_error = str(exc)[:500]
        error_code = raw_error if raw_error in {
            "QUIZ_TRANSLATION_ALIGNMENT_FAILED",
            "QUIZ_JSON_PARSE_FAILED",
            "QUIZ_SCHEMA_INVALID",
            "QUIZ_APPLICATION_INVALID",
            "QUIZ_LLM_EMPTY",
        } else None
        public_error = {
            "QUIZ_TRANSLATION_ALIGNMENT_FAILED": (
                "英文と日本語訳の文対応を確認できなかったため、5回試行後にQuiz生成を停止しました。"
                "時間をおいてもう一度生成してください。"
            ),
            "QUIZ_JSON_PARSE_FAILED": (
                "生成結果の形式を確認できなかったため、Quiz生成を停止しました。"
            ),
            "QUIZ_SCHEMA_INVALID": (
                "生成結果の内容を確認できなかったため、Quiz生成を停止しました。"
                "時間をおいてもう一度生成してください。"
            ),
            "QUIZ_APPLICATION_INVALID": (
                "指定条件に合うQuizを生成できなかったため、Quiz生成を停止しました。"
                "条件を見直してもう一度生成してください。"
            ),
            "QUIZ_LLM_EMPTY": (
                "生成結果を受け取れなかったため、Quiz生成を停止しました。"
                "時間をおいてもう一度生成してください。"
            ),
        }.get(
            error_code,
            "Quiz生成を完了できませんでした。時間をおいてもう一度生成してください。",
        )
        logger.warning(
            "quiz_generation_job_failed",
            job_id=job_id,
            reason_code=error_code or "QUIZ_GENERATION_FAILED",
            error_type=type(exc).__name__,
        )
        async with _quiz_generation_lock:
            _update_job_record(
                store,
                job_id,
                status="failed",
                error=public_error,
                error_code=error_code,
                clock=clock,
            )
        return
    async with _quiz_generation_lock:
        _update_job_record(store, job_id, status="succeeded", quiz=quiz, clock=clock)
