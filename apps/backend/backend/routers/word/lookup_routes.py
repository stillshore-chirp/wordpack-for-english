from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query, Request

from ...auth import principal_from_request
from ...application.wordpack.lookup_wordpack import (
    WordLookupResponse,
    build_lookup_response,
)
from ...authorization.policies import ResourceVisibility, ensure_read_allowed
from ...models.word import WordPackRequest, _validate_lemma
from .dependencies import (
    get_run_wordpack_flow,
    get_store,
    get_word_pack_visibility,
    next_word_pack_id,
    run_wordpack_flow as default_run_wordpack_flow,
)
from .error_mapping import generation_error_mapping

router = APIRouter()


@router.get("/", response_model=WordLookupResponse, response_model_exclude_none=True)
async def lookup_word(
    request: Request, lemma: str = Query(..., description="見出し語")
) -> WordLookupResponse:
    """WordPack を lemma で取得し、定義と例文を返す。"""

    normalized_lemma = str(lemma or "").strip()
    if not normalized_lemma:
        raise HTTPException(status_code=400, detail="lemma is required")
    try:
        _validate_lemma(normalized_lemma)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid lemma: {exc}") from exc

    repository = get_store()
    stored = repository.find_word_pack_by_lemma_ci(normalized_lemma)
    if stored:
        word_pack_id, stored_lemma, stored_sense_title = stored
        packed = repository.get_word_pack(word_pack_id)
        if packed is None:
            raise HTTPException(status_code=404, detail="word pack not found")

        visibility = get_word_pack_visibility(repository, word_pack_id) or {}
        ensure_read_allowed(
            principal_from_request(request),
            ResourceVisibility(
                exists=True,
                guest_public=bool(visibility.get("guest_public", False)),
                owner_user_id=visibility.get("owner_user_id"),
                not_found_detail="word pack not found",
            ),
        )

        lemma_from_store, data_json, created_at, updated_at = packed
        try:
            data_dict = json.loads(data_json) if data_json else {}
        except json.JSONDecodeError:
            data_dict = {}
        return build_lookup_response(
            lemma=lemma_from_store,
            sense_title=stored_sense_title,
            word_pack_id=word_pack_id,
            word_pack_data=data_dict,
            created_at=created_at,
            updated_at=updated_at,
        )

    principal = principal_from_request(request)
    if principal.is_guest:
        raise HTTPException(
            status_code=403, detail="Guest mode cannot generate WordPack"
        )

    flow = get_run_wordpack_flow()
    if flow is default_run_wordpack_flow:
        # なぜ: GET /api/word は閲覧専用エンドポイントであり、
        #       通常運用では未登録語の生成・保存を POST 系 API に集約するため。
        raise HTTPException(status_code=404, detail="WordPack not found")

    req = WordPackRequest(lemma=normalized_lemma)
    word_pack, _ = await flow(
        lemma=normalized_lemma,
        req_opts=req,
        scope=req.regenerate_scope,
        http_error_mapping=generation_error_mapping(),
    )
    word_pack_id = next_word_pack_id()
    repository.save_word_pack(
        word_pack_id,
        normalized_lemma,
        word_pack.model_dump_json(),
        metadata={"owner_user_id": principal.user_id},
    )

    packed = repository.get_word_pack(word_pack_id)
    if packed is not None:
        lemma_from_store, data_json, created_at, updated_at = packed
        try:
            data_dict = json.loads(data_json) if data_json else {}
        except json.JSONDecodeError:
            data_dict = word_pack.model_dump(mode="json")
        return build_lookup_response(
            lemma=lemma_from_store,
            sense_title=word_pack.sense_title,
            word_pack_id=word_pack_id,
            word_pack_data=data_dict,
            created_at=created_at,
            updated_at=updated_at,
        )

    return build_lookup_response(
        lemma=word_pack.lemma,
        sense_title=word_pack.sense_title,
        word_pack_id=word_pack_id,
        word_pack_data=word_pack.model_dump(mode="json"),
        created_at="",
        updated_at="",
    )
