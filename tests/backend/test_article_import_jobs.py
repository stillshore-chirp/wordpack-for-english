from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.application.article.import_jobs import (  # noqa: E402
    enqueue_article_import_job,
    get_article_import_job,
)
from backend.models.article import ArticleDetailResponse, ArticleImportRequest  # noqa: E402


class _IdGenerator:
    def new_id(self) -> str:
        return "article-import-job:test"


class _Store:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    def create_article_import_job(
        self,
        *,
        job_id: str,
        owner_user_id: str,
        request_fingerprint: str,
        status: str,
    ) -> dict[str, Any]:
        record = {
            "job_id": job_id,
            "owner_user_id": owner_user_id,
            "request_fingerprint": request_fingerprint,
            "status": status,
            "article_id": None,
            "error": None,
        }
        self.jobs[job_id] = record
        return dict(record)

    def update_article_import_job(
        self,
        job_id: str,
        *,
        status: str,
        article_id: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        record = self.jobs.get(job_id)
        if record is None:
            return None
        record["status"] = status
        if article_id is not None:
            record["article_id"] = article_id
        if error is not None:
            record["error"] = error
        return dict(record)

    def get_article_import_job(self, job_id: str) -> dict[str, Any] | None:
        record = self.jobs.get(job_id)
        return dict(record) if record is not None else None


def _article(article_id: str = "art:test") -> ArticleDetailResponse:
    return ArticleDetailResponse(
        id=article_id,
        title_en="Title",
        body_en="Body",
        body_ja="本文",
        created_at="2026-07-31T00:00:00Z",
        updated_at="2026-07-31T00:00:00Z",
    )


def test_article_import_job_succeeds_and_is_owner_scoped() -> None:
    asyncio.run(_assert_article_import_job_succeeds_and_is_owner_scoped())


async def _assert_article_import_job_succeeds_and_is_owner_scoped() -> None:
    store = _Store()
    req = ArticleImportRequest(text="hello")

    await enqueue_article_import_job(
        req,
        owner_user_id="user-1",
        store=store,
        runner=lambda _req: _article(),
        scheduler=None,
        id_generator=_IdGenerator(),
    )

    job = await get_article_import_job(
        "article-import-job:test",
        owner_user_id="user-1",
        store=store,
    )
    assert job is not None
    assert job.status == "succeeded"
    assert job.article_id == "art:test"
    assert (
        await get_article_import_job(
            "article-import-job:test",
            owner_user_id="user-2",
            store=store,
        )
        is None
    )


def test_article_import_job_records_failure_without_exposing_exception() -> None:
    asyncio.run(_assert_article_import_job_records_failure())


async def _assert_article_import_job_records_failure() -> None:
    store = _Store()

    def _raise(_req: ArticleImportRequest) -> ArticleDetailResponse:
        raise RuntimeError("provider timeout")

    await enqueue_article_import_job(
        ArticleImportRequest(text="hello"),
        owner_user_id="user-1",
        store=store,
        runner=_raise,
        scheduler=None,
        id_generator=_IdGenerator(),
    )

    job = await get_article_import_job(
        "article-import-job:test",
        owner_user_id="user-1",
        store=store,
    )
    assert job is not None
    assert job.status == "failed"
    assert job.error == "provider timeout"


def test_article_import_job_submission_is_idempotent() -> None:
    asyncio.run(_assert_article_import_job_submission_is_idempotent())


async def _assert_article_import_job_submission_is_idempotent() -> None:
    store = _Store()
    calls = 0

    def _run(_req: ArticleImportRequest) -> ArticleDetailResponse:
        nonlocal calls
        calls += 1
        return _article()

    first = await enqueue_article_import_job(
        ArticleImportRequest(text="hello"),
        owner_user_id="user-1",
        store=store,
        runner=_run,
        scheduler=None,
        id_generator=_IdGenerator(),
        job_id="article-import-job:client-generated",
    )
    second = await enqueue_article_import_job(
        ArticleImportRequest(text="hello"),
        owner_user_id="user-1",
        store=store,
        runner=_run,
        scheduler=None,
        id_generator=_IdGenerator(),
        job_id="article-import-job:client-generated",
    )

    assert first.job_id == second.job_id == "article-import-job:client-generated"
    assert first.status == "queued"
    assert second.status == "succeeded"
    assert calls == 1

    try:
        await enqueue_article_import_job(
            ArticleImportRequest(text="different article"),
            owner_user_id="user-1",
            store=store,
            runner=_run,
            scheduler=None,
            id_generator=_IdGenerator(),
            job_id="article-import-job:client-generated",
        )
    except PermissionError:
        pass
    else:  # pragma: no cover - assertion guard
        raise AssertionError("another article import must not reuse the job ID")
