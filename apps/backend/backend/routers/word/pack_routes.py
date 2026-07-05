from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ...auth import principal_from_request
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.policies import (
    ResourceVisibility,
    ensure_read_allowed,
    ensure_user_write_allowed,
)
from ...authorization.principal import Principal
from ...application.wordpack.create_empty_wordpack import build_empty_wordpack
from ...infrastructure.llm.empty_wordpack_title import (
    EmptyWordPackTitleGenerationError,
    generate_sense_title_for_empty_wordpack,
)
from ...models.word import (
    WordPack,
    WordPackCreateRequest,
    WordPackListItem,
    WordPackListResponse,
)
from .dependencies import get_store, get_word_pack_visibility, next_word_pack_id

router = APIRouter()


@router.post(
    "/packs",
    response_model=dict,
    summary="空のWordPackを作成して保存",
    response_description="作成されたWordPackのIDを返します",
)
async def create_empty_word_pack(
    req: WordPackCreateRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_CREATE)),
) -> dict:
    """空のWordPackを作成・保存する（sense_title は短い日本語をLLMで生成）。"""

    lemma = req.lemma.strip()
    if not lemma:
        raise HTTPException(status_code=400, detail="lemma is required")

    try:
        generated_title = generate_sense_title_for_empty_wordpack(lemma)
    except EmptyWordPackTitleGenerationError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "message": "LLM failed to generate sense_title (strict mode)",
                "reason_code": "LLM_FAILURE",
                "diagnostics": {"lemma": lemma, "error": str(exc)[:200]},
            },
        ) from exc
    empty_word_pack = build_empty_wordpack(lemma, generated_title=generated_title)
    word_pack_id = next_word_pack_id()
    get_store().save_word_pack(
        word_pack_id,
        lemma,
        empty_word_pack.model_dump_json(),
        metadata={"owner_user_id": principal.user_id},
    )

    return {"id": word_pack_id}


@router.get(
    "/packs",
    response_model=WordPackListResponse,
    summary="保存済みWordPack一覧を取得",
    response_description="保存済みWordPackの一覧を返します",
)
async def list_word_packs(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200, description="取得件数上限"),
    offset: int = Query(default=0, ge=0, description="オフセット"),
) -> WordPackListResponse:
    """保存済みWordPackの一覧を取得する。"""

    repository = get_store()
    principal = principal_from_request(request)
    if principal.is_guest:
        items_with_flags = repository.list_public_word_packs_with_flags(
            limit=limit, offset=offset
        )
        total = repository.count_public_word_packs()
    else:
        items_with_flags = repository.list_word_packs_with_flags(
            limit=limit, offset=offset
        )
        total = repository.count_word_packs()
    items: list[WordPackListItem] = []
    for (
        wp_id,
        lemma,
        sense_title,
        created_at,
        updated_at,
        is_empty,
        examples_count,
        checked_only,
        learned,
        guest_public,
    ) in items_with_flags:
        items.append(
            WordPackListItem(
                id=wp_id,
                lemma=lemma,
                sense_title=sense_title,
                created_at=created_at,
                updated_at=updated_at,
                is_empty=bool(is_empty),
                examples_count=examples_count,
                checked_only_count=checked_only,
                learned_count=learned,
                guest_public=guest_public,
            )
        )

    return WordPackListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/packs/{word_pack_id}",
    response_model=WordPack,
    response_model_exclude_none=True,
    summary="保存済みWordPackを取得",
    response_description="指定されたIDのWordPackを返します",
)
async def get_word_pack(request: Request, word_pack_id: str) -> WordPack:
    """保存済みWordPackをIDで取得する。"""

    repository = get_store()
    result = repository.get_word_pack(word_pack_id)
    if result is None:
        raise HTTPException(status_code=404, detail="WordPack not found")

    _lemma, data, _created_at, _updated_at = result
    visibility = get_word_pack_visibility(repository, word_pack_id) or {}
    guest_public = bool(visibility.get("guest_public", False))
    ensure_read_allowed(
        principal_from_request(request),
        ResourceVisibility(
            exists=True,
            guest_public=guest_public,
            owner_user_id=visibility.get("owner_user_id"),
            not_found_detail="WordPack not found",
        ),
    )
    try:
        word_pack_dict = json.loads(data)
        word_pack_dict["guest_public"] = guest_public
        return WordPack.model_validate(word_pack_dict)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=f"Invalid WordPack data: {exc}")


@router.delete(
    "/packs/{word_pack_id}",
    summary="WordPackを削除",
    response_description="指定されたIDのWordPackを削除します",
)
async def delete_word_pack(
    word_pack_id: str,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_DELETE)),
) -> dict[str, str]:
    """保存済みWordPackを削除する。"""

    repository = get_store()
    visibility = get_word_pack_visibility(repository, word_pack_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="WordPack not found",
    )
    success = repository.delete_word_pack(word_pack_id)
    if not success:
        raise HTTPException(status_code=404, detail="WordPack not found")

    return {"message": "WordPack deleted successfully"}
