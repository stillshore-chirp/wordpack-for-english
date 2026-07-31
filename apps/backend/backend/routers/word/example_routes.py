from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status

from ...application.wordpack.errors import handle_flow_runtime_error
from ...application.common.generation_jobs import (
    GenerationJobResponse,
    enqueue_generation_job,
    get_generation_job,
)
from ...authorization.dependencies import require_user_permission
from ...authorization.permissions import Permission
from ...authorization.policies import ensure_user_write_allowed
from ...authorization.principal import Principal
from ...config import settings
from ...infrastructure.llm.wordpack_generator import build_llm_info, get_override_value
from ...flows.word_pack import WordPackFlow
from ...models.word import (
    ExampleCategory,
    ExampleListItem,
    ExampleListResponse,
    ExamplesBulkDeleteRequest,
    ExamplesBulkDeleteResponse,
    ExampleTranscriptionTypingRequest,
    ExampleTranscriptionTypingResponse,
)
from ...providers import get_llm_provider
from ...infrastructure.runtime import AsyncioTaskScheduler, PrefixedUuidGenerator
from .dependencies import get_store, get_word_pack_visibility
from .error_mapping import example_error_mapping
from .schemas import ExamplesGenerateRequest

router = APIRouter()


class EmptyExampleGenerationError(RuntimeError):
    reason_code = "EMPTY_CONTENT"

    def __init__(self, *, lemma: str, category: ExampleCategory) -> None:
        super().__init__("LLM returned no usable examples")
        self.diagnostics = {"lemma": lemma, "category": category.value}


def _generate_and_append_examples(
    *,
    repository: object,
    word_pack_id: str,
    lemma: str,
    category: ExampleCategory,
    req: ExamplesGenerateRequest,
) -> dict[str, Any]:
    llm = get_llm_provider(
        model_override=get_override_value(req, "model"),
        reasoning_override=get_override_value(req, "reasoning"),
        text_override=get_override_value(req, "text"),
    )
    llm_info = build_llm_info(req)
    flow = WordPackFlow(chroma_client=None, llm=llm, llm_info=llm_info)
    generated = flow.generate_examples_for_categories(lemma, {category: 2})
    items = [
        {
            "en": item.en,
            "ja": item.ja,
            "grammar_ja": item.grammar_ja,
            "llm_model": item.llm_model,
            "llm_params": item.llm_params,
        }
        for item in generated.get(category, [])
    ]
    if not items:
        raise EmptyExampleGenerationError(lemma=lemma, category=category)
    added = repository.append_examples(word_pack_id, category.value, items)
    return {
        "message": "Examples generated and appended",
        "word_pack_id": word_pack_id,
        "lemma": lemma,
        "added": added,
        "category": category.value,
        "items": items,
    }


@router.delete(
    "/packs/{word_pack_id}/examples/{category}/{index}",
    summary="保存済みWordPackから個々の例文を削除",
    response_description="指定カテゴリ内の index の例文を削除します",
)
async def delete_example_from_word_pack(
    word_pack_id: str,
    category: ExampleCategory,
    index: int,
    principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_DELETE)),
) -> dict[str, object]:
    """保存済みWordPackから個々の例文を削除する（正規化テーブルを直接操作）。"""

    repository = get_store()
    wp = repository.get_word_pack(word_pack_id)
    if wp is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    visibility = get_word_pack_visibility(repository, word_pack_id) or {}
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="WordPack not found",
    )

    remaining = repository.delete_example(word_pack_id, category.value, index)
    if remaining is None:
        raise HTTPException(status_code=404, detail="Example index out of range")

    return {
        "message": "Example deleted",
        "category": category.value,
        "index": index,
        "remaining": remaining,
    }


@router.post(
    "/packs/{word_pack_id}/examples/{category}/generate",
    summary="カテゴリ別の例文を2件追加生成して保存",
)
async def generate_examples_for_word_pack(
    word_pack_id: str,
    category: ExampleCategory,
    req: ExamplesGenerateRequest | None = None,
    principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_CREATE)),
) -> dict[str, Any]:
    """保存済みWordPackに、指定カテゴリの例文を2件追加生成して保存する。"""

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

    req = req or ExamplesGenerateRequest()
    try:
        return _generate_and_append_examples(
            repository=repository,
            word_pack_id=word_pack_id,
            lemma=lemma,
            category=category,
            req=req,
        )
    except RuntimeError as exc:
        handle_flow_runtime_error(
            exc,
            lemma=lemma,
            strict_mode=settings.strict_mode,
            error_mapping=example_error_mapping(category.value),
        )
        raise


@router.post(
    "/packs/{word_pack_id}/examples/{category}/generate/jobs",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="カテゴリ別の例文追加生成ジョブを開始",
)
async def create_examples_generation_job(
    word_pack_id: str,
    category: ExampleCategory,
    req: ExamplesGenerateRequest | None = None,
    principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_CREATE)),
) -> GenerationJobResponse:
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
    request_options = req or ExamplesGenerateRequest()

    try:
        return await enqueue_generation_job(
            owner_user_id=principal.user_id,
            job_type="example-generation",
            store=repository,
            runner=lambda: _generate_and_append_examples(
                repository=repository,
                word_pack_id=word_pack_id,
                lemma=lemma,
                category=category,
                req=request_options,
            ),
            scheduler=AsyncioTaskScheduler(),
            id_generator=PrefixedUuidGenerator("example-generation-job:"),
            job_id=(
                f"example-generation-job:{request_options.client_job_id}"
                if request_options.client_job_id is not None
                else None
            ),
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.get(
    "/packs/{word_pack_id}/examples/{category}/generate/jobs/{job_id}",
    response_model=GenerationJobResponse,
    summary="カテゴリ別の例文追加生成ジョブの状態を取得",
)
async def get_examples_generation_job_status(
    word_pack_id: str,
    category: ExampleCategory,
    job_id: str,
    principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_READ)),
) -> GenerationJobResponse:
    repository = get_store()
    visibility = get_word_pack_visibility(repository, word_pack_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="WordPack not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="WordPack not found",
    )
    job = await get_generation_job(
        job_id,
        owner_user_id=principal.user_id,
        expected_job_type="example-generation",
        store=repository,
    )
    result = job.result if job is not None else None
    if (
        job is None
        or (
            result is not None
            and (
                result.get("word_pack_id") != word_pack_id
                or result.get("category") != category.value
            )
        )
    ):
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


@router.get(
    "/examples",
    response_model=ExampleListResponse,
    summary="例文一覧を取得（WordPackを横断）",
)
async def list_examples(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200, description="取得件数上限"),
    offset: int = Query(default=0, ge=0, description="オフセット"),
    order_by: str = Query(
        default="created_at", description="created_at|pack_updated_at|lemma|category"
    ),
    order_dir: str = Query(default="desc", description="asc|desc"),
    search: Optional[str] = Query(
        default=None, description="英文に対する検索文字列（部分一致等）"
    ),
    search_mode: str = Query(default="contains", description="prefix|suffix|contains"),
    category: Optional[ExampleCategory] = Query(
        default=None, description="カテゴリで絞り込み"
    ),
) -> ExampleListResponse:
    """`word_pack_examples` を元に横断的な例文一覧を返す。"""

    repository = get_store()
    public_only = bool(getattr(request.state, "guest", False))
    items_raw = repository.list_examples(
        limit=limit,
        offset=offset,
        order_by=order_by,
        order_dir=order_dir,
        search=search,
        search_mode=search_mode,
        category=category.value if category is not None else None,
        public_only=public_only,
    )
    total = repository.count_examples(
        search=search,
        search_mode=search_mode,
        category=category.value if category is not None else None,
        public_only=public_only,
    )

    items: list[ExampleListItem] = []
    for (
        rid,
        wp_id,
        lemma,
        cat,
        en,
        ja,
        grammar_ja,
        created_at,
        pack_updated_at,
        checked_only_count,
        learned_count,
        transcription_typing_count,
    ) in items_raw:
        items.append(
            ExampleListItem(
                id=rid,
                word_pack_id=wp_id,
                lemma=lemma,
                category=ExampleCategory(cat),
                en=en,
                ja=ja,
                grammar_ja=grammar_ja,
                created_at=created_at,
                word_pack_updated_at=pack_updated_at,
                checked_only_count=checked_only_count,
                learned_count=learned_count,
                transcription_typing_count=transcription_typing_count,
            )
        )
    return ExampleListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/examples/bulk-delete",
    response_model=ExamplesBulkDeleteResponse,
    summary="例文をID指定で一括削除",
)
async def bulk_delete_examples(
    req: ExamplesBulkDeleteRequest,
    _principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_DELETE)),
) -> ExamplesBulkDeleteResponse:
    """例文IDのリストを受け取り、一括で削除する。"""

    deleted, not_found = get_store().delete_examples_by_ids(req.ids)
    return ExamplesBulkDeleteResponse(deleted=deleted, not_found=not_found)


@router.post(
    "/examples/{example_id}/transcription-typing",
    response_model=ExampleTranscriptionTypingResponse,
    summary="例文の文字起こし練習入力を記録",
)
async def update_example_transcription_typing(
    example_id: int,
    req: ExampleTranscriptionTypingRequest,
    _principal: Principal = Depends(require_user_permission(Permission.EXAMPLE_UPDATE)),
) -> ExampleTranscriptionTypingResponse:
    """入力長の妥当性を確認しつつ文字起こしカウントを加算する。"""

    try:
        updated = get_store().update_example_transcription_typing(
            example_id, req.input_length
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Example not found")
    return ExampleTranscriptionTypingResponse(transcription_typing_count=updated)
