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
from ..common.generation_jobs import fingerprint_generation_request


ArticleImportRunner = Callable[[ArticleImportRequest], ArticleDetailResponse]


@dataclass
class ArticleImportJob:
    job_id: str
    owner_user_id: str
    request_fingerprint: str
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
        request_fingerprint=str(record.get("request_fingerprint") or ""),
        status=status,  # type: ignore[arg-type]
        article_id=str(record.get("article_id") or "") or None,
        error=str(error) if error is not None else None,
    )


def _create_job_record(
    store: object,
    job_id: str,
    owner_user_id: str,
    request_fingerprint: str,
) -> tuple[ArticleImportJob, bool]:
    if _store_supports_persistent_jobs(store):
        record = store.create_article_import_job(
            job_id=job_id,
            owner_user_id=owner_user_id,
            request_fingerprint=request_fingerprint,
            status="queued",
        )
        return _job_from_record(record), bool(record.get("_created", True))
    return (
        ArticleImportJob(
            job_id=job_id,
            owner_user_id=owner_user_id,
            request_fingerprint=request_fingerprint,
            status="queued",
        ),
        True,
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
    job_id: str | None = None,
) -> ArticleImportJobResponse:
    resolved_job_id = job_id or id_generator.new_id()
    request_fingerprint = fingerprint_generation_request(
        "article-import",
        req.model_dump(mode="json"),
    )
    async with _article_import_lock:
        existing = _get_job_record(store, resolved_job_id)
        if existing is not None:
            if (
                existing.owner_user_id != owner_user_id
                or existing.request_fingerprint != request_fingerprint
            ):
                raise PermissionError("Article import job ID is already in use")
            return existing.to_response()
        job, created = _create_job_record(
            store,
            resolved_job_id,
            owner_user_id,
            request_fingerprint,
        )
        if (
            job.owner_user_id != owner_user_id
            or job.request_fingerprint != request_fingerprint
        ):
            raise PermissionError("Article import job ID is already in use")
        _article_import_jobs[resolved_job_id] = job
        if not created:
            return job.to_response()
    if scheduler is None:
        await _run_article_import_job(
            resolved_job_id,
            req,
            store=store,
            runner=runner,
        )
    else:
        scheduler.spawn(
            _run_article_import_job(
                resolved_job_id,
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
