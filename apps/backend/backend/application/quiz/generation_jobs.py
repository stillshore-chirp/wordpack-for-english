from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from ...logging import logger
from ...models.quiz import Quiz, QuizGenerateRequest, QuizGenerationJobResponse
from ..common.ports import Clock, IdGenerator, TaskScheduler


class QuizGenerator(Protocol):
    async def generate(self, req: QuizGenerateRequest, store: object) -> Quiz:
        raise NotImplementedError


@dataclass
class QuizGenerationJob:
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    quiz_id: str | None = None
    result: Quiz | None = None
    error: str | None = None
    created_at: str = ""
    updated_at: str = ""

    def to_response(self) -> QuizGenerationJobResponse:
        return QuizGenerationJobResponse(
            job_id=self.job_id,
            status=self.status,
            quiz_id=self.quiz_id,
            result=self.result,
            error=self.error,
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
    return QuizGenerationJob(
        job_id=str(record.get("job_id") or ""),
        status=status,  # type: ignore[arg-type]
        quiz_id=str(record.get("quiz_id") or "") or None,
        result=result,
        error=str(error) if error is not None else None,
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
) -> QuizGenerationJob | None:
    if _store_supports_persistent_jobs(store):
        record = store.update_quiz_generation_job(
            job_id,
            status=status,
            quiz_id=quiz.id if quiz is not None else None,
            result_json=quiz.model_dump_json() if quiz is not None else None,
            error=error,
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
    try:
        quiz = await generator.generate(req, store)
    except Exception as exc:
        async with _quiz_generation_lock:
            _update_job_record(
                store,
                job_id,
                status="failed",
                error=str(exc)[:500],
                clock=clock,
            )
        return
    async with _quiz_generation_lock:
        _update_job_record(store, job_id, status="succeeded", quiz=quiz, clock=clock)
