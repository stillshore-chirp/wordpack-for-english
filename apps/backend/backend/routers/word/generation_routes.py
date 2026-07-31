from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from ...application.common.generation_jobs import (
    GenerationJobResponse,
    enqueue_generation_job,
    fingerprint_generation_request,
    get_generation_job,
)
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.principal import Principal
from ...infrastructure.runtime import AsyncioTaskScheduler, PrefixedUuidGenerator
from ...logging import logger
from ...models.word import GeneratedWordPackResponse, WordPackRequest
from .dependencies import get_run_wordpack_flow, get_store, next_word_pack_id
from .error_mapping import generation_error_mapping

router = APIRouter()


async def _generate_and_save_word_pack(
    req: WordPackRequest,
    *,
    owner_user_id: str,
) -> dict[str, object]:
    word_pack, _ = await get_run_wordpack_flow()(
        lemma=req.lemma,
        req_opts=req,
        scope=req.regenerate_scope,
        http_error_mapping=generation_error_mapping(),
    )
    word_pack_id = next_word_pack_id()
    get_store().save_word_pack(
        word_pack_id,
        req.lemma,
        word_pack.model_dump_json(),
        metadata={"owner_user_id": owner_user_id},
    )
    return GeneratedWordPackResponse(
        id=word_pack_id,
        **word_pack.model_dump(),
    ).model_dump(exclude_none=True)


@router.post(
    "/pack/jobs",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="WordPack生成ジョブを開始",
)
async def enqueue_word_pack_generation(
    req: WordPackRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_GENERATE)),
) -> GenerationJobResponse:
    try:
        return await enqueue_generation_job(
            owner_user_id=principal.user_id,
            job_type="wordpack-generation",
            request_fingerprint=fingerprint_generation_request(
                "wordpack-generation",
                req.model_dump(mode="json", exclude={"client_job_id"}),
            ),
            store=get_store(),
            async_runner=lambda: _generate_and_save_word_pack(
                req,
                owner_user_id=principal.user_id,
            ),
            scheduler=AsyncioTaskScheduler(),
            id_generator=PrefixedUuidGenerator("wordpack-generation-job:"),
            job_id=(
                f"wordpack-generation-job:{req.client_job_id}"
                if req.client_job_id is not None
                else None
            ),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/pack/jobs/{job_id}",
    response_model=GenerationJobResponse,
    summary="WordPack生成ジョブの状態を取得",
)
async def get_word_pack_generation_job(
    job_id: str,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_GENERATE)),
) -> GenerationJobResponse:
    job = await get_generation_job(
        job_id,
        owner_user_id=principal.user_id,
        expected_job_type="wordpack-generation",
        store=get_store(),
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@router.post(
    "/pack",
    response_model=GeneratedWordPackResponse,
    response_model_exclude_none=True,
    summary="WordPack を生成",
    response_description="生成された WordPack を返します",
)
async def generate_word_pack(
    req: WordPackRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_GENERATE)),
) -> GeneratedWordPackResponse:
    """Generate a new word pack using LangGraph flow."""

    try:
        logger.info(
            "wordpack_generate_request",
            lemma=req.lemma,
            pronunciation_enabled=req.pronunciation_enabled,
            regenerate_scope=str(req.regenerate_scope),
        )
        result = await _generate_and_save_word_pack(
            req,
            owner_user_id=principal.user_id,
        )
        response = GeneratedWordPackResponse.model_validate(result)

        logger.info(
            "wordpack_generate_response",
            lemma=response.lemma,
            senses_count=len(response.senses),
            examples_total=(
                len(response.examples.Dev)
                + len(response.examples.CS)
                + len(response.examples.LLM)
                + len(response.examples.Business)
                + len(response.examples.Common)
            ),
            has_definition_any=any(bool(s.definition_ja) for s in response.senses),
        )
        return response
    except RuntimeError:
        # run_wordpack_flow 内で HTTPException へ変換済み。それ以外は上位へ委譲。
        raise
