from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel

from ...logging import logger
from ...models.word import WordPack, WordPackRegenerateRequest
from ..common.errors import NotFoundError
from ..common.ports import IdGenerator, TaskScheduler


class RegenerateJob(BaseModel):
    job_id: str
    word_pack_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    result: WordPack | None = None
    error: str | None = None


WordPackFlowRunner = Callable[..., Awaitable[tuple[WordPack, dict[str, Any]]]]

store: object | None = None
run_wordpack_flow: WordPackFlowRunner | None = None
_regenerate_jobs: dict[str, RegenerateJob] = {}
_regenerate_lock = asyncio.Lock()


def _repository(repository: object | None) -> object:
    selected = repository if repository is not None else store
    if selected is None:
        raise RuntimeError("regenerate job repository is not configured")
    return selected


def _flow_runner(flow: WordPackFlowRunner | None) -> WordPackFlowRunner:
    selected = flow if flow is not None else run_wordpack_flow
    if selected is None:
        raise RuntimeError("regenerate job flow runner is not configured")
    return selected


def _store_supports_persistent_jobs(repository: object) -> bool:
    return all(
        callable(getattr(repository, name, None))
        for name in (
            "create_regenerate_job",
            "update_regenerate_job",
            "get_regenerate_job",
        )
    )


def _job_from_record(
    record: Mapping[str, object],
    *,
    result: WordPack | None = None,
) -> RegenerateJob:
    status = str(record.get("status") or "pending")
    if status not in {"pending", "running", "succeeded", "failed"}:
        status = "failed"
    error = record.get("error")
    if result is None and record.get("result_json") is not None:
        try:
            result = WordPack.model_validate_json(str(record.get("result_json")))
        except Exception as exc:  # pragma: no cover - defensive logging for corrupt data
            logger.error(
                "wordpack_regenerate_result_parse_failed",
                word_pack_id=str(record.get("word_pack_id") or ""),
                job_id=str(record.get("job_id") or ""),
                error_type=exc.__class__.__name__,
                error_message=str(exc)[:200],
            )
    return RegenerateJob(
        job_id=str(record.get("job_id") or ""),
        word_pack_id=str(record.get("word_pack_id") or ""),
        status=status,  # type: ignore[arg-type]
        result=result,
        error=str(error) if error is not None else None,
    )


def _create_job_record(
    repository: object, job_id: str, word_pack_id: str
) -> RegenerateJob:
    if _store_supports_persistent_jobs(repository):
        record = repository.create_regenerate_job(
            job_id=job_id,
            word_pack_id=word_pack_id,
            status="pending",
        )
        return _job_from_record(record)
    return RegenerateJob(
        job_id=job_id, word_pack_id=word_pack_id, status="pending", result=None
    )


def _update_job_record(
    repository: object,
    job_id: str,
    *,
    status: Literal["pending", "running", "succeeded", "failed"],
    error: str | None = None,
    result: WordPack | None = None,
) -> RegenerateJob | None:
    if _store_supports_persistent_jobs(repository):
        record = repository.update_regenerate_job(
            job_id,
            status=status,
            error=error,
            result_json=result.model_dump_json() if result is not None else None,
        )
        if record is None:
            return None
        return _job_from_record(record)
    job = _regenerate_jobs.get(job_id)
    if not job:
        return None
    job.status = status
    if error is not None:
        job.error = error
    if result is not None:
        job.result = result
    _regenerate_jobs[job_id] = job
    return job


def _get_job_record(repository: object, job_id: str) -> RegenerateJob | None:
    if _store_supports_persistent_jobs(repository):
        record = repository.get_regenerate_job(job_id)
        if record is None:
            return None
        return _job_from_record(record)
    return _regenerate_jobs.get(job_id)


async def run_regenerate_job(
    job_id: str,
    word_pack_id: str,
    req: WordPackRegenerateRequest,
    *,
    repository: object | None = None,
    flow: WordPackFlowRunner | None = None,
    error_mapping: Mapping[str, Callable[..., Exception]] | None = None,
) -> None:
    repository = _repository(repository)
    flow = _flow_runner(flow)
    async with _regenerate_lock:
        job = _update_job_record(repository, job_id, status="running")
        if not job:
            return
    try:
        result = repository.get_word_pack(word_pack_id)
        if result is None:
            raise NotFoundError("WordPack not found")
        lemma, _, _, _ = result
        word_pack, _ = await flow(
            lemma=lemma,
            req_opts=req,
            scope=req.regenerate_scope,
            error_mapping=error_mapping,
        )
        repository.save_word_pack(word_pack_id, lemma, word_pack.model_dump_json())
        async with _regenerate_lock:
            _update_job_record(repository, job_id, status="succeeded", result=word_pack)
        logger.info(
            "wordpack_regenerate_async_succeeded",
            word_pack_id=word_pack_id,
            lemma=lemma,
            job_id=job_id,
        )
    except Exception as exc:
        err_msg = str(exc)
        async with _regenerate_lock:
            _update_job_record(repository, job_id, status="failed", error=err_msg[:500])
        logger.error(
            "wordpack_regenerate_async_failed",
            word_pack_id=word_pack_id,
            job_id=job_id,
            error_type=exc.__class__.__name__,
            error_message=err_msg[:200],
        )


async def enqueue_regenerate_job(
    word_pack_id: str,
    req: WordPackRegenerateRequest,
    *,
    repository: object | None = None,
    flow: WordPackFlowRunner | None = None,
    scheduler: TaskScheduler | None = None,
    id_generator: IdGenerator | None = None,
    error_mapping: Mapping[str, Callable[..., Exception]] | None = None,
) -> RegenerateJob:
    repository = _repository(repository)
    flow = _flow_runner(flow)
    if repository.get_word_pack(word_pack_id) is None:
        raise NotFoundError("WordPack not found")
    job_id = id_generator.new_id() if id_generator else f"job:{len(_regenerate_jobs) + 1}"
    job = _create_job_record(repository, job_id, word_pack_id)
    async with _regenerate_lock:
        _regenerate_jobs[job_id] = job
    if scheduler is None:
        await run_regenerate_job(
            job_id,
            word_pack_id,
            req,
            repository=repository,
            flow=flow,
            error_mapping=error_mapping,
        )
    else:
        scheduler.spawn(
            run_regenerate_job(
                job_id,
                word_pack_id,
                req,
                repository=repository,
                flow=flow,
                error_mapping=error_mapping,
            )
        )
    logger.info(
        "wordpack_regenerate_async_enqueued",
        word_pack_id=word_pack_id,
        job_id=job_id,
        regenerate_scope=req.regenerate_scope,
    )
    return job


async def get_regenerate_job(
    word_pack_id: str,
    job_id: str,
    *,
    repository: object | None = None,
) -> RegenerateJob:
    repository = _repository(repository)
    async with _regenerate_lock:
        job = _get_job_record(repository, job_id)
    if job is None or job.word_pack_id != word_pack_id:
        raise NotFoundError("Job not found")
    return job
