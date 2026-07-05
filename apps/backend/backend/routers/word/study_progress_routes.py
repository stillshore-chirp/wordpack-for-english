from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...application.wordpack.study_progress import study_progress_increments
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.principal import Principal
from ...models.word import (
    ExampleStudyProgressResponse,
    StudyProgressRequest,
    WordPackStudyProgressResponse,
)
from .dependencies import get_store

router = APIRouter()


@router.post(
    "/packs/{word_pack_id}/study-progress",
    response_model=WordPackStudyProgressResponse,
    summary="WordPackの学習進捗を記録",
)
async def update_word_pack_study_progress(
    word_pack_id: str,
    req: StudyProgressRequest,
    _principal: Principal = Depends(require_user_permission(Permission.WORDPACK_UPDATE)),
) -> WordPackStudyProgressResponse:
    """WordPack単位の確認/学習済みカウントを更新する。"""

    checked_increment, learned_increment = study_progress_increments(req.kind)
    result = get_store().update_word_pack_study_progress(
        word_pack_id, checked_increment, learned_increment
    )
    if result is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    checked_only_count, learned_count = result
    return WordPackStudyProgressResponse(
        checked_only_count=checked_only_count,
        learned_count=learned_count,
    )


@router.post(
    "/examples/{example_id}/study-progress",
    response_model=ExampleStudyProgressResponse,
    summary="例文の学習進捗を記録",
)
async def update_example_study_progress(
    example_id: int,
    req: StudyProgressRequest,
    _principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_UPDATE)),
) -> ExampleStudyProgressResponse:
    """例文単位の確認/学習済みカウントを更新する。"""

    checked_increment, learned_increment = study_progress_increments(req.kind)
    result = get_store().update_example_study_progress(
        example_id, checked_increment, learned_increment
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Example not found")
    word_pack_id, checked_only_count, learned_count = result
    return ExampleStudyProgressResponse(
        id=example_id,
        word_pack_id=word_pack_id,
        checked_only_count=checked_only_count,
        learned_count=learned_count,
    )
