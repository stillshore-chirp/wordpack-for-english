from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

import anyio
from pydantic import BaseModel

from ...logging import logger
from .ports import IdGenerator, TaskScheduler

GenerationJobType = Literal["category-generate-import", "example-generation"]
GenerationJobStatus = Literal["queued", "running", "succeeded", "failed"]
GenerationRunner = Callable[[], Mapping[str, Any]]


class GenerationJobResponse(BaseModel):
    job_id: str
    job_type: GenerationJobType
    status: GenerationJobStatus
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class GenerationJob:
    job_id: str
    owner_user_id: str
    job_type: GenerationJobType
    status: GenerationJobStatus
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_response(self) -> GenerationJobResponse:
        return GenerationJobResponse(
            job_id=self.job_id,
            job_type=self.job_type,
            status=self.status,
            result=self.result,
            error=self.error,
        )


_generation_jobs: dict[str, GenerationJob] = {}
_generation_jobs_lock = asyncio.Lock()


def _supports_persistent_jobs(store: object) -> bool:
    return all(
        callable(getattr(store, name, None))
        for name in (
            "create_generation_job",
            "update_generation_job",
            "get_generation_job",
        )
    )


def _job_from_record(record: Mapping[str, object]) -> GenerationJob:
    status = str(record.get("status") or "queued")
    if status not in {"queued", "running", "succeeded", "failed"}:
        status = "failed"
    job_type = str(record.get("job_type") or "")
    if job_type not in {"category-generate-import", "example-generation"}:
        raise ValueError("Unsupported generation job type")
    result: dict[str, Any] | None = None
    result_json = record.get("result_json")
    if result_json:
        parsed = json.loads(str(result_json))
        if isinstance(parsed, dict):
            result = parsed
    error = record.get("error")
    return GenerationJob(
        job_id=str(record.get("job_id") or ""),
        owner_user_id=str(record.get("owner_user_id") or ""),
        job_type=job_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        result=result,
        error=str(error) if error is not None else None,
    )


def _create_job(
    store: object,
    *,
    job_id: str,
    owner_user_id: str,
    job_type: GenerationJobType,
) -> GenerationJob:
    if _supports_persistent_jobs(store):
        return _job_from_record(
            store.create_generation_job(
                job_id=job_id,
                owner_user_id=owner_user_id,
                job_type=job_type,
                status="queued",
            )
        )
    return GenerationJob(job_id, owner_user_id, job_type, "queued")


def _update_job(
    store: object,
    job_id: str,
    *,
    status: GenerationJobStatus,
    result: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> GenerationJob | None:
    result_dict = dict(result) if result is not None else None
    if _supports_persistent_jobs(store):
        record = store.update_generation_job(
            job_id,
            status=status,
            result_json=json.dumps(result_dict, ensure_ascii=False)
            if result_dict is not None
            else None,
            error=error,
        )
        return _job_from_record(record) if record is not None else None
    job = _generation_jobs.get(job_id)
    if job is None:
        return None
    job.status = status
    if result_dict is not None:
        job.result = result_dict
    if error is not None:
        job.error = error
    return job


def _get_job(store: object, job_id: str) -> GenerationJob | None:
    if _supports_persistent_jobs(store):
        record = store.get_generation_job(job_id)
        return _job_from_record(record) if record is not None else None
    return _generation_jobs.get(job_id)


async def _run_generation_job(
    job_id: str,
    *,
    store: object,
    runner: GenerationRunner,
) -> None:
    async with _generation_jobs_lock:
        if _update_job(store, job_id, status="running") is None:
            return
    try:
        result = await anyio.to_thread.run_sync(runner)
    except Exception as exc:
        error = str(exc)[:500]
        async with _generation_jobs_lock:
            _update_job(store, job_id, status="failed", error=error)
        logger.error(
            "generation_job_failed",
            job_id=job_id,
            error_type=exc.__class__.__name__,
            error_message=error[:200],
        )
        return
    async with _generation_jobs_lock:
        _update_job(store, job_id, status="succeeded", result=result)
    logger.info("generation_job_succeeded", job_id=job_id)


async def enqueue_generation_job(
    *,
    owner_user_id: str,
    job_type: GenerationJobType,
    store: object,
    runner: GenerationRunner,
    scheduler: TaskScheduler | None,
    id_generator: IdGenerator,
) -> GenerationJobResponse:
    job_id = id_generator.new_id()
    job = _create_job(
        store,
        job_id=job_id,
        owner_user_id=owner_user_id,
        job_type=job_type,
    )
    async with _generation_jobs_lock:
        _generation_jobs[job_id] = job
    coroutine = _run_generation_job(job_id, store=store, runner=runner)
    if scheduler is None:
        await coroutine
    else:
        scheduler.spawn(coroutine)
    return job.to_response()


async def get_generation_job(
    job_id: str,
    *,
    owner_user_id: str,
    expected_job_type: GenerationJobType,
    store: object,
) -> GenerationJobResponse | None:
    async with _generation_jobs_lock:
        job = _get_job(store, job_id)
    if (
        job is None
        or job.owner_user_id != owner_user_id
        or job.job_type != expected_job_type
    ):
        return None
    return job.to_response()
