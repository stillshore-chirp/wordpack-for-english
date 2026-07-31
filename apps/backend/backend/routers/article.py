"""Article ルーター。backend.providers パッケージの新構造に追随する。"""

from __future__ import annotations

import json
import uuid
from functools import partial
from typing import Any

import anyio
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, ValidationError, field_validator

from ..application.article.import_jobs import (
    enqueue_article_import_job,
    get_article_import_job,
)
from ..application.common.generation_jobs import (
    GenerationJobResponse,
    enqueue_generation_job,
    get_generation_job,
)
from ..auth import principal_from_request
from ..authorization.dependencies import require_user_permission
from ..authorization.permissions import Permission
from ..authorization.policies import (
    ResourceVisibility,
    ensure_read_allowed,
    ensure_user_write_allowed,
)
from ..authorization.principal import Principal
from ..config import settings
from ..domain.article.lemma_filter import STOP_LEMMAS, filter_article_lemmas
from ..flows.article_import import ArticleImportFlow
from ..flows.category_generate_import import CategoryGenerateAndImportFlow
from ..logging import logger
from ..llm_models import (
    ensure_supported_llm_model,
    ensure_supported_reasoning_options,
    ensure_supported_text_options,
)
from ..models.article import (
    ARTICLE_IMPORT_TEXT_MAX_LENGTH,
    ArticleDetailResponse,
    ArticleGuestPublicUpdateRequest,
    ArticleGuestPublicUpdateResponse,
    ArticleImportRequest,
    ArticleImportJobResponse,
    ArticleListItem,
    ArticleListResponse,
    ArticleWordPackLink,
)
from ..infrastructure.runtime import AsyncioTaskScheduler, PrefixedUuidGenerator
from ..models.word import ExampleCategory
from ..observability import request_trace, span
from ..store import store as _default_store
from ..store.proxy import CurrentStoreProxy


router = APIRouter(tags=["article"])
store = CurrentStoreProxy(_default_store)


def _prompt_for_article_import(text: str) -> str:
    """原文保持・機能語除外の厳格プロンプト。"""
    return (
        """以下の英語テキストが与えられる。出力は次のキーだけを含む JSON に限定し、その他の情報は一切出力しない。
- title_en: 10語以内の非常に短い英語タイトル。
- body_ja: 入力テキストを忠実に訳した日本語（要約や言い換えは禁止）。
- notes_ja: 用法や文脈に焦点を当てた日本語の短い解説（1〜3文）。
- lemmas: 学習価値のある lemma/フレーズのみ（重複禁止）。厳格フィルタ: 機能語（冠詞・助動詞・be 動詞・単純な代名詞・基本的な前置詞/接続詞）や、'I','am','a','the','be','is','are','to','of','and','in','on','for','with','at','by','from','as' などの些末語を除外する。
  学術/専門的な語彙や複数語表現（句動詞・イディオム・コロケーション）を含める。
  目安は 5〜30 件。
重要: 入力テキストを言い換えたり書き換えたりしない。
返却形式: {"title_en", "body_ja", "notes_ja", "lemmas"} のキーだけを含む JSON。
入力テキスト:
"""
        + text
    )


_STOP_LEMMAS: set[str] = STOP_LEMMAS


def _post_filter_lemmas(raw: list[str]) -> list[str]:
    """LLM抽出結果に対しルールベースで簡易フィルタを適用。"""
    return filter_article_lemmas(raw)


def _build_text_too_long_error() -> dict[str, Any]:
    """記事インポートテキスト超過時の標準化されたエラーボディを生成する。"""

    return {
        "error": "article_import_text_too_long",
        "message": (
            "文章インポートのテキストは"
            f"{ARTICLE_IMPORT_TEXT_MAX_LENGTH}文字以内で入力してください。"
        ),
        "max_length": ARTICLE_IMPORT_TEXT_MAX_LENGTH,
    }


def _validate_import_request(payload: dict[str, Any]) -> ArticleImportRequest:
    """ArticleImportRequest の検証を行い、文字数超過時のみ 413 を通知する。"""

    try:
        return ArticleImportRequest.model_validate(payload)
    except ValidationError as exc:  # FastAPI の 422 を尊重しつつ 413 を上書き
        for err in exc.errors():
            if err.get("type") == "string_too_long" and tuple(err.get("loc", ())) == ("text",):
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=_build_text_too_long_error(),
                ) from exc
        raise RequestValidationError(exc.errors()) from exc


@router.post(
    "/import", response_model=ArticleDetailResponse, response_model_exclude_none=True
)
async def import_article(
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_CREATE)),
) -> ArticleDetailResponse:
    """文章インポートを受け付け、文字数超過は 413 で通知する。"""

    req = _validate_import_request(payload)
    return _run_article_import(
        req,
        owner_user_id=principal.user_id,
        endpoint="/api/article/import",
    )


def _run_article_import(
    req: ArticleImportRequest,
    *,
    owner_user_id: str,
    endpoint: str,
) -> ArticleDetailResponse:
    flow = ArticleImportFlow(owner_user_id=owner_user_id)
    with request_trace(
        name="ArticleImportFlow", metadata={"endpoint": endpoint}
    ) as ctx:
        tr = ctx.get("trace") if isinstance(ctx, dict) else None  # type: ignore[assignment]
        with span(
            trace=tr, name="article.flow.run", input={"text_chars": len(req.text or "")}
        ) as _:
            return flow.run(req)


@router.post(
    "/import/jobs",
    response_model=ArticleImportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="文章インポートジョブを開始",
)
async def create_article_import_job(
    payload: dict[str, Any] = Body(...),
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_CREATE)),
) -> ArticleImportJobResponse:
    """Firebase Hosting の同期上限を避け、文章インポートを非同期実行する。"""

    request_payload = dict(payload)
    client_job_id = request_payload.pop("client_job_id", None)
    resolved_job_id: str | None = None
    if client_job_id is not None:
        try:
            resolved_job_id = f"article-import-job:{uuid.UUID(str(client_job_id))}"
        except (ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="client_job_id must be a UUID",
            ) from exc

    req = _validate_import_request(request_payload)
    try:
        return await enqueue_article_import_job(
            req,
            owner_user_id=principal.user_id,
            store=store,
            runner=partial(
                _run_article_import,
                owner_user_id=principal.user_id,
                endpoint="/api/article/import/jobs",
            ),
            scheduler=AsyncioTaskScheduler(),
            id_generator=PrefixedUuidGenerator("article-import-job:"),
            job_id=resolved_job_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get(
    "/import/jobs/{job_id}",
    response_model=ArticleImportJobResponse,
    summary="文章インポートジョブの状態を取得",
)
async def get_article_import_job_status(
    job_id: str,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_READ)),
) -> ArticleImportJobResponse:
    job = await get_article_import_job(
        job_id,
        owner_user_id=principal.user_id,
        store=store,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Article import job not found")
    return job


@router.get("/", response_model=ArticleListResponse)
async def list_articles(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)
) -> ArticleListResponse:
    principal = principal_from_request(request)
    public_only = principal.is_guest
    owner_user_id = (
        principal.user_id
        if principal.is_user and getattr(settings, "enforce_owner_scoping", False)
        else None
    )
    items_raw = store.list_articles(
        limit=limit,
        offset=offset,
        public_only=public_only,
        owner_user_id=owner_user_id,
    )
    items = [
        ArticleListItem(
            id=i[0],
            title_en=i[1],
            created_at=i[2],
            updated_at=i[3],
            guest_public=bool(i[4]),
        )
        for i in items_raw
    ]
    total = store.count_articles(public_only=public_only, owner_user_id=owner_user_id)
    return ArticleListResponse(items=items, total=total, limit=limit, offset=offset)


# Trailing-slashless alias to avoid 307 redirects in some environments
@router.get("", response_model=ArticleListResponse, include_in_schema=False)
async def list_articles_no_slash(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)
) -> ArticleListResponse:
    return await list_articles(request=request, limit=limit, offset=offset)


async def _get_article_response(request: Request, article_id: str) -> ArticleDetailResponse:
    result = store.get_article(article_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Article not found")
    (
        title_en,
        body_en,
        body_ja,
        notes_ja,
        llm_model,
        llm_params,
        generation_category,
        created_at,
        updated_at,
        generation_started_at,
        generation_completed_at,
        generation_duration_ms,
        guest_public,
        links,
    ) = result
    principal = principal_from_request(request)
    visibility = store.get_article_visibility(article_id) or {}
    ensure_read_allowed(
        principal,
        ResourceVisibility(
            exists=True,
            guest_public=bool(guest_public),
            owner_user_id=visibility.get("owner_user_id"),
            not_found_detail="Article not found",
        ),
    )
    is_guest = principal.is_guest
    duration_value = (
        int(generation_duration_ms)
        if isinstance(generation_duration_ms, (int, float))
        and not isinstance(generation_duration_ms, bool)
        else None
    )
    link_models: list[ArticleWordPackLink] = []
    for wp_id, lemma, status in links:
        if is_guest and not store.is_word_pack_guest_public(wp_id):
            continue
        is_empty = True
        try:
            got = store.get_word_pack(wp_id)
            if got is not None:
                _, data_json, _, _ = got
                d = json.loads(data_json)
                senses_empty = not d.get("senses")
                ex = d.get("examples") or {}
                examples_empty = all(
                    not (ex.get(k) or [])
                    for k in ["Dev", "CS", "LLM", "Business", "Common"]
                )
                study_empty = not bool((d.get("study_card") or "").strip())
                is_empty = bool(senses_empty and examples_empty and study_empty)
        except Exception:
            is_empty = True
        link_models.append(
            ArticleWordPackLink(
                word_pack_id=wp_id, lemma=lemma, status=status, is_empty=is_empty
            )
        )
    return ArticleDetailResponse(
        id=article_id,
        title_en=title_en,
        body_en=body_en,
        body_ja=body_ja,
        notes_ja=notes_ja,
        llm_model=llm_model,
        llm_params=llm_params,
        generation_category=generation_category,
        related_word_packs=link_models,
        created_at=created_at,
        updated_at=updated_at,
        generation_started_at=generation_started_at,
        generation_completed_at=generation_completed_at,
        generation_duration_ms=duration_value,
        guest_public=bool(guest_public),
    )


@router.get(
    "/{article_id}",
    response_model=ArticleDetailResponse,
    response_model_exclude_none=True,
)
async def get_article(request: Request, article_id: str) -> ArticleDetailResponse:
    return await _get_article_response(request, article_id)


@router.post(
    "/{article_id}/guest-public",
    response_model=ArticleGuestPublicUpdateResponse,
    summary="Reader記事のゲスト公開フラグを更新",
)
async def update_article_guest_public(
    article_id: str,
    req: ArticleGuestPublicUpdateRequest,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_UPDATE)),
) -> ArticleGuestPublicUpdateResponse:
    visibility = store.get_article_visibility(article_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="Article not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="Article not found",
    )
    updated = store.update_article_guest_public(article_id, req.guest_public)
    if updated is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleGuestPublicUpdateResponse(
        article_id=article_id,
        guest_public=updated,
    )


@router.delete("/{article_id}")
async def delete_article(
    article_id: str,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_DELETE)),
) -> dict[str, str]:
    visibility = store.get_article_visibility(article_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="Article not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="Article not found",
    )
    ok = store.delete_article(article_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"message": "Article deleted"}


class CategoryGenerateImportRequest(BaseModel):
    category: ExampleCategory = Field(description="例文カテゴリ")
    model: str | None = None
    reasoning: dict | None = None
    text: dict | None = None

    @field_validator("model")
    @classmethod
    def ensure_model_supported(cls, value: str | None) -> str | None:
        return ensure_supported_llm_model(value) if value else value

    @field_validator("reasoning")
    @classmethod
    def ensure_reasoning_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_reasoning_options(value)

    @field_validator("text")
    @classmethod
    def ensure_text_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_text_options(value)


@router.post("/generate_and_import")
async def generate_and_import_examples(
    req: CategoryGenerateImportRequest,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_CREATE)),
) -> dict[str, object]:
    """選択カテゴリに関連する語を1つ生成し、空のWordPackを作成、
    当該カテゴリの例文を2件生成して保存し、それぞれを文章インポートに渡して記事化する。
    """
    flow = CategoryGenerateAndImportFlow(
        model=getattr(req, "model", None),
        reasoning=getattr(req, "reasoning", None),
        text=getattr(req, "text", None),
        owner_user_id=principal.user_id,
    )
    with request_trace(
        name="CategoryGenerateAndImportFlow",
        metadata={"endpoint": "/api/article/generate_and_import"},
    ) as ctx:
        tr = ctx.get("trace") if isinstance(ctx, dict) else None  # type: ignore[assignment]
        with span(
            trace=tr,
            name="article.category_generate_and_import",
            input={"category": req.category.value},
        ):
            # フローは同期実装のため、イベントループをブロックしないようスレッドにオフロード
            result = await anyio.to_thread.run_sync(partial(flow.run, req.category))
            return result


@router.post(
    "/generate_and_import/jobs",
    response_model=GenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="カテゴリ例文生成・記事化ジョブを開始",
)
async def create_generate_and_import_job(
    req: CategoryGenerateImportRequest,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_CREATE)),
) -> GenerationJobResponse:
    """カテゴリ例文生成から記事保存までを、再接続可能な非同期ジョブとして開始する。"""

    def runner() -> dict[str, object]:
        flow = CategoryGenerateAndImportFlow(
            model=req.model,
            reasoning=req.reasoning,
            text=req.text,
            owner_user_id=principal.user_id,
        )
        with request_trace(
            name="CategoryGenerateAndImportFlow",
            metadata={"endpoint": "/api/article/generate_and_import/jobs"},
        ) as ctx:
            trace = ctx.get("trace") if isinstance(ctx, dict) else None
            with span(
                trace=trace,
                name="article.category_generate_and_import",
                input={"category": req.category.value},
            ):
                return flow.run(req.category)

    return await enqueue_generation_job(
        owner_user_id=principal.user_id,
        job_type="category-generate-import",
        store=store,
        runner=runner,
        scheduler=AsyncioTaskScheduler(),
        id_generator=PrefixedUuidGenerator("category-generate-import-job:"),
    )


@router.get(
    "/generate_and_import/jobs/{job_id}",
    response_model=GenerationJobResponse,
    summary="カテゴリ例文生成・記事化ジョブの状態を取得",
)
async def get_generate_and_import_job_status(
    job_id: str,
    principal: Principal = Depends(require_user_permission(Permission.ARTICLE_READ)),
) -> GenerationJobResponse:
    job = await get_generation_job(
        job_id,
        owner_user_id=principal.user_id,
        expected_job_type="category-generate-import",
        store=store,
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job
