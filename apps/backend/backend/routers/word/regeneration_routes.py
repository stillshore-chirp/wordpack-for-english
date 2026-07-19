from __future__ import annotations

from importlib import import_module

from fastapi import APIRouter, Depends, HTTPException

from ...application.common.errors import NotFoundError
from ...application.wordpack import regenerate_jobs as regenerate_jobs_module
from ...application.wordpack.regenerate_jobs import (
    RegenerateJob,
    _regenerate_jobs,
    _regenerate_lock,
    enqueue_regenerate_job,
    get_regenerate_job,
)
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.policies import ensure_user_write_allowed
from ...authorization.principal import Principal
from ...infrastructure.runtime import AsyncioTaskScheduler, UuidHexGenerator
from ...models.word import WordPack, WordPackRegenerateRequest
from .dependencies import get_run_wordpack_flow, get_store, get_word_pack_visibility
from .error_mapping import regeneration_error_mapping

router = APIRouter()


def _sync_legacy_regenerate_job_registry() -> None:
    package = import_module("backend.routers.word")
    regenerate_jobs_module._regenerate_jobs = getattr(
        package, "_regenerate_jobs", _regenerate_jobs
    )
    regenerate_jobs_module._regenerate_lock = getattr(
        package, "_regenerate_lock", _regenerate_lock
    )


@router.post(
    "/packs/{word_pack_id}/regenerate",
    response_model=WordPack,
    response_model_exclude_none=True,
    summary="WordPackを再生成",
    response_description="既存のWordPackを再生成して返します",
)
async def regenerate_word_pack(
    word_pack_id: str,
    req: WordPackRegenerateRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_UPDATE)),
) -> WordPack:
    """既存のWordPackを再生成する。"""

    repository = get_store()
    result = repository.get_word_pack(word_pack_id)
    if result is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    visibility = get_word_pack_visibility(repository, word_pack_id) or {}
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="WordPack not found",
    )

    lemma, _, _, _ = result

    try:
        word_pack, _ = await get_run_wordpack_flow()(
            lemma=lemma,
            req_opts=req,
            scope=req.regenerate_scope,
            error_mapping=regeneration_error_mapping(),
        )

        repository.save_word_pack(
            word_pack_id,
            lemma,
            word_pack.model_dump_json(),
            metadata={"owner_user_id": principal.user_id},
        )
        return word_pack
    except RuntimeError:
        # run_wordpack_flow 内で HTTPException へ変換済み。それ以外は既定処理へ委譲。
        raise


@router.post(
    "/packs/{word_pack_id}/regenerate/async",
    response_model=RegenerateJob,
    status_code=202,
    summary="WordPackを非同期で再生成（ジョブIDを返す）",
)
async def enqueue_regenerate_word_pack(
    word_pack_id: str,
    req: WordPackRegenerateRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_UPDATE)),
) -> RegenerateJob:
    """Enqueue an async regenerate job and return job ID immediately."""

    _sync_legacy_regenerate_job_registry()
    repository = get_store()
    visibility = get_word_pack_visibility(repository, word_pack_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="WordPack not found",
    )
    try:
        return await enqueue_regenerate_job(
            word_pack_id,
            req,
            repository=repository,
            flow=get_run_wordpack_flow(),
            scheduler=AsyncioTaskScheduler(),
            id_generator=UuidHexGenerator(),
            error_mapping=regeneration_error_mapping(),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/packs/{word_pack_id}/regenerate/jobs/{job_id}",
    response_model=RegenerateJob,
    summary="非同期再生成ジョブの状態を取得",
)
async def get_regenerate_job_status(
    word_pack_id: str, job_id: str
) -> RegenerateJob:
    """Return current job status and result when available."""

    _sync_legacy_regenerate_job_registry()
    try:
        return await get_regenerate_job(
            word_pack_id,
            job_id,
            repository=get_store(),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
