from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

import anyio

from ...logging import logger
from ...models.article import (
    ArticleDetailResponse,
    ArticleImportJobResponse,
    ArticleImportRequest,
)
from ..common.ports import IdGenerator, TaskScheduler


ArticleImportRunner = Callable[[ArticleImportRequest], ArticleDetailResponse]


@dataclass
class ArticleImportJob:
    job_id: str
    owner_user_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    article_id: str | None = None
    error: str | None = None

    def to_response(self) -> ArticleImportJobResponse:
        return ArticleImportJobResponse(
            job_id=self.job_id,
            status=self.status,
            article_id=self.article_id,
            error=self.error,
        )


_article_import_jobs: dict[str, ArticleImportJob] = {}
_article_import_lock = asyncio.Lock()


def _store_supports_persistent_jobs(store: object) -> bool:
    return all(
        callable(getattr(store, name, None))
        for name in (
            "create_article_import_job",
            "update_article_import_job",
            "get_article_import_job",
        )
    )


def _job_from_record(record: Mapping[str, object]) -> ArticleImportJob:
    status = str(record.get("status") or "queued")
    if status not in {"queued", "running", "succeeded", "failed"}:
        status = "failed"
    error = record.get("error")
    return ArticleImportJob(
        job_id=str(record.get("job_id") or ""),
        owner_user_id=str(record.get("owner_user_id") or ""),
        status=status,  # type: ignore[arg-type]
        article_id=str(record.get("article_id") or "") or None,
        error=str(error) if error is not None else None,
    )


def _create_job_record(
    store: object,
    job_id: str,
    owner_user_id: str,
) -> ArticleImportJob:
    if _store_supports_persistent_jobs(store):
        return _job_from_record(
            store.create_article_import_job(
                job_id=job_id,
                owner_user_id=owner_user_id,
                status="queued",
            )
        )
    return ArticleImportJob(
        job_id=job_id,
        owner_user_id=owner_user_id,
        status="queued",
    )


def _update_job_record(
    store: object,
    job_id: str,
    *,
    status: Literal["queued", "running", "succeeded", "failed"],
    article_id: str | None = None,
    error: str | None = None,
) -> ArticleImportJob | None:
    if _store_supports_persistent_jobs(store):
        record = store.update_article_import_job(
            job_id,
            status=status,
            article_id=article_id,
            error=error,
        )
        return _job_from_record(record) if record is not None else None
    job = _article_import_jobs.get(job_id)
    if job is None:
        return None
    job.status = status
    if article_id is not None:
        job.article_id = article_id
    if error is not None:
        job.error = error
    _article_import_jobs[job_id] = job
    return job


def _get_job_record(store: object, job_id: str) -> ArticleImportJob | None:
    if _store_supports_persistent_jobs(store):
        record = store.get_article_import_job(job_id)
        return _job_from_record(record) if record is not None else None
    return _article_import_jobs.get(job_id)


async def _run_article_import_job(
    job_id: str,
    req: ArticleImportRequest,
    *,
    store: object,
    runner: ArticleImportRunner,
) -> None:
    async with _article_import_lock:
        if _update_job_record(store, job_id, status="running") is None:
            return
    try:
        result = await anyio.to_thread.run_sync(runner, req)
    except Exception as exc:
        error = str(exc)[:500]
        async with _article_import_lock:
            _update_job_record(store, job_id, status="failed", error=error)
        logger.error(
            "article_import_async_failed",
            job_id=job_id,
            error_type=exc.__class__.__name__,
            error_message=error[:200],
        )
        return
    async with _article_import_lock:
        _update_job_record(
            store,
            job_id,
            status="succeeded",
            article_id=result.id,
        )
    logger.info(
        "article_import_async_succeeded",
        job_id=job_id,
        article_id=result.id,
    )


async def enqueue_article_import_job(
    req: ArticleImportRequest,
    *,
    owner_user_id: str,
    store: object,
    runner: ArticleImportRunner,
    scheduler: TaskScheduler | None,
    id_generator: IdGenerator,
) -> ArticleImportJobResponse:
    job_id = id_generator.new_id()
    job = _create_job_record(store, job_id, owner_user_id)
    async with _article_import_lock:
        _article_import_jobs[job_id] = job
    if scheduler is None:
        await _run_article_import_job(
            job_id,
            req,
            store=store,
            runner=runner,
        )
    else:
        scheduler.spawn(
            _run_article_import_job(
                job_id,
                req,
                store=store,
                runner=runner,
            )
        )
    return job.to_response()


async def get_article_import_job(
    job_id: str,
    *,
    owner_user_id: str,
    store: object,
) -> ArticleImportJobResponse | None:
    async with _article_import_lock:
        job = _get_job_record(store, job_id)
    if job is None or job.owner_user_id != owner_user_id:
        return None
    return job.to_response()
