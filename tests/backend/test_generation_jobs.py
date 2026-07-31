from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.application.common.generation_jobs import (  # noqa: E402
    enqueue_generation_job,
    get_generation_job,
)


class _IdGenerator:
    def new_id(self) -> str:
        return "generation-job:test"


class _Store:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}

    def create_generation_job(
        self,
        *,
        job_id: str,
        owner_user_id: str,
        job_type: str,
        status: str,
    ) -> dict[str, Any]:
        record = {
            "job_id": job_id,
            "owner_user_id": owner_user_id,
            "job_type": job_type,
            "status": status,
            "result_json": None,
            "error": None,
        }
        self.jobs[job_id] = record
        return dict(record)

    def update_generation_job(
        self,
        job_id: str,
        *,
        status: str,
        result_json: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        record = self.jobs.get(job_id)
        if record is None:
            return None
        record["status"] = status
        if result_json is not None:
            record["result_json"] = result_json
        if error is not None:
            record["error"] = error
        return dict(record)

    def get_generation_job(self, job_id: str) -> dict[str, Any] | None:
        record = self.jobs.get(job_id)
        return dict(record) if record is not None else None


def test_generation_job_persists_result_and_enforces_owner_and_type() -> None:
    asyncio.run(_assert_generation_job_persists_result_and_enforces_scope())


async def _assert_generation_job_persists_result_and_enforces_scope() -> None:
    store = _Store()
    await enqueue_generation_job(
        owner_user_id="user-1",
        job_type="example-generation",
        store=store,
        runner=lambda: {"word_pack_id": "wp:test", "category": "Dev", "added": 2},
        scheduler=None,
        id_generator=_IdGenerator(),
    )

    job = await get_generation_job(
        "generation-job:test",
        owner_user_id="user-1",
        expected_job_type="example-generation",
        store=store,
    )
    assert job is not None
    assert job.status == "succeeded"
    assert job.result == {"word_pack_id": "wp:test", "category": "Dev", "added": 2}
    assert (
        await get_generation_job(
            "generation-job:test",
            owner_user_id="user-2",
            expected_job_type="example-generation",
            store=store,
        )
        is None
    )
    assert (
        await get_generation_job(
            "generation-job:test",
            owner_user_id="user-1",
            expected_job_type="category-generate-import",
            store=store,
        )
        is None
    )


def test_generation_job_records_runner_failure() -> None:
    asyncio.run(_assert_generation_job_records_runner_failure())


async def _assert_generation_job_records_runner_failure() -> None:
    store = _Store()

    def fail() -> dict[str, Any]:
        raise RuntimeError("provider timeout")

    await enqueue_generation_job(
        owner_user_id="user-1",
        job_type="category-generate-import",
        store=store,
        runner=fail,
        scheduler=None,
        id_generator=_IdGenerator(),
    )
    job = await get_generation_job(
        "generation-job:test",
        owner_user_id="user-1",
        expected_job_type="category-generate-import",
        store=store,
    )
    assert job is not None
    assert job.status == "failed"
    assert job.error == "provider timeout"
