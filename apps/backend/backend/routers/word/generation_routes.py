from __future__ import annotations

from fastapi import APIRouter, Depends

from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.principal import Principal
from ...logging import logger
from ...models.word import GeneratedWordPackResponse, WordPackRequest
from .dependencies import get_run_wordpack_flow, get_store, next_word_pack_id
from .error_mapping import generation_error_mapping

router = APIRouter()


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
            metadata={"owner_user_id": principal.user_id},
        )

        logger.info(
            "wordpack_generate_response",
            lemma=word_pack.lemma,
            senses_count=len(word_pack.senses),
            examples_total=(
                len(word_pack.examples.Dev)
                + len(word_pack.examples.CS)
                + len(word_pack.examples.LLM)
                + len(word_pack.examples.Business)
                + len(word_pack.examples.Common)
            ),
            has_definition_any=any(bool(s.definition_ja) for s in word_pack.senses),
        )
        return GeneratedWordPackResponse(id=word_pack_id, **word_pack.model_dump())
    except RuntimeError:
        # run_wordpack_flow 内で HTTPException へ変換済み。それ以外は上位へ委譲。
        raise
