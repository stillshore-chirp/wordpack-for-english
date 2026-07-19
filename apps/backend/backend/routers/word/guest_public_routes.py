from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...application.common.errors import NotFoundError
from ...application.wordpack.guest_public import (
    UpdateWordPackGuestPublicCommand,
    update_guest_public_flag,
)
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.policies import ensure_user_write_allowed
from ...authorization.principal import Principal
from ...infrastructure.runtime import SystemClock
from ...logging import logger
from ...models.word import WordPackGuestPublicRequest, WordPackGuestPublicResponse
from .dependencies import get_store, get_word_pack_visibility

router = APIRouter()


@router.post(
    "/packs/{word_pack_id}/guest-public",
    response_model=WordPackGuestPublicResponse,
    summary="WordPackのゲスト公開フラグを更新",
)
async def update_word_pack_guest_public(
    request: Request,
    word_pack_id: str,
    req: WordPackGuestPublicRequest,
    principal: Principal = Depends(require_user_permission(Permission.WORDPACK_UPDATE)),
) -> WordPackGuestPublicResponse:
    """WordPack単位のゲスト公開フラグを更新する。"""

    command = UpdateWordPackGuestPublicCommand(
        word_pack_id=word_pack_id,
        guest_public=req.guest_public,
        updated_at=SystemClock().now_iso(),
    )
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
        result = update_guest_public_flag(repository=repository, command=command)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    logger.info(
        "wordpack_guest_public_updated",
        word_pack_id=word_pack_id,
        user_id=getattr(request.state, "user_id", None),
        guest_public=req.guest_public,
    )
    return WordPackGuestPublicResponse(
        word_pack_id=result.word_pack_id,
        guest_public=result.guest_public,
    )
