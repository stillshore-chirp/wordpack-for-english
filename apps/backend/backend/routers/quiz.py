from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from ..application.quiz.generation_jobs import enqueue_quiz_generation_job, get_quiz_generation_job
from ..application.quiz.scoring import score_quiz_attempt
from ..auth import principal_from_request
from ..authorization.dependencies import require_user_permission
from ..authorization.permissions import Permission
from ..authorization.policies import (
    ResourceVisibility,
    ensure_read_allowed,
    ensure_user_write_allowed,
)
from ..authorization.principal import Principal
from ..infrastructure.llm.quiz_generator import QuizGenerateFlowAdapter
from ..infrastructure.runtime import AsyncioTaskScheduler, PrefixedUuidGenerator, SystemClock
from ..models.quiz import (
    Quiz,
    QuizAttemptRequest,
    QuizAttemptResponse,
    QuizGenerateRequest,
    QuizGenerationJobResponse,
    QuizGuestPublicUpdateRequest,
    QuizGuestPublicUpdateResponse,
    QuizListItem,
    QuizListResponse,
    QuizWordPackLink,
)
from .word.dependencies import get_store

router = APIRouter(tags=["quiz"])


def _question_count(quiz: Quiz) -> int:
    return sum(len(section.questions) for section in quiz.sections)


def _list_item_from_quiz(quiz: Quiz) -> QuizListItem:
    return QuizListItem(
        id=quiz.id,
        title_en=quiz.title_en,
        format_profile=quiz.format_profile,
        generation_domain=quiz.generation_domain,
        domain_intensity=quiz.domain_intensity,
        difficulty=quiz.difficulty,
        question_count=_question_count(quiz),
        passage_count=len(quiz.passages),
        source_lemmas=quiz.source_lemmas,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        guest_public=quiz.guest_public,
    )


def _is_empty_word_pack(repository: object, word_pack_id: str) -> bool:
    metadata = repository.get_word_pack_metadata(word_pack_id)
    if not isinstance(metadata, Mapping):
        return False
    counts = metadata.get("examples_category_counts") or {}
    if not isinstance(counts, Mapping):
        return False
    return sum(int(value or 0) for value in counts.values()) == 0


def _rehydrate_related_word_pack_links(repository: object, quiz: Quiz) -> Quiz:
    links: list[QuizWordPackLink] = []
    changed = False
    for link in quiz.related_word_packs:
        if link.word_pack_id or link.status == "skipped":
            links.append(link)
            continue
        word_pack_id = repository.find_word_pack_id_by_lemma(link.lemma)
        if not word_pack_id:
            links.append(link)
            continue
        links.append(
            link.model_copy(
                update={
                    "word_pack_id": word_pack_id,
                    "status": "existing",
                    "is_empty": _is_empty_word_pack(repository, word_pack_id),
                }
            )
        )
        changed = True
    return quiz.model_copy(update={"related_word_packs": links}) if changed else quiz


@router.post(
    "/generate/jobs",
    response_model=QuizGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Quiz生成ジョブを開始",
)
async def create_quiz_generation_job(
    req: QuizGenerateRequest,
    principal: Principal = Depends(require_user_permission(Permission.QUIZ_CREATE)),
) -> QuizGenerationJobResponse:
    return await enqueue_quiz_generation_job(
        req,
        get_store(),
        generator=QuizGenerateFlowAdapter(owner_user_id=principal.user_id),
        scheduler=AsyncioTaskScheduler(),
        id_generator=PrefixedUuidGenerator("quiz-job:"),
        clock=SystemClock(),
    )


@router.get(
    "/generate/jobs/{job_id}",
    response_model=QuizGenerationJobResponse,
    summary="Quiz生成ジョブの状態を取得",
)
async def get_quiz_generation_job_status(
    job_id: str,
    _principal: Principal = Depends(require_user_permission(Permission.QUIZ_READ)),
) -> QuizGenerationJobResponse:
    job = await get_quiz_generation_job(job_id, get_store(), clock=SystemClock())
    if job is None:
        raise HTTPException(status_code=404, detail="Quiz generation job not found")
    return job


@router.get(
    "",
    response_model=QuizListResponse,
    summary="保存済みQuiz一覧を取得",
)
async def list_quizzes(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> QuizListResponse:
    repository = get_store()
    public_only = principal_from_request(request).is_guest
    rows = repository.list_quizzes(limit=limit, offset=offset, public_only=public_only)
    total = repository.count_quizzes(public_only=public_only)
    items = [_list_item_from_quiz(Quiz.model_validate(row)) for row in rows]
    return QuizListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{quiz_id}",
    response_model=Quiz,
    summary="保存済みQuiz詳細を取得",
)
async def get_quiz(request: Request, quiz_id: str) -> Quiz:
    repository = get_store()
    row = repository.get_quiz(quiz_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz = Quiz.model_validate(row)
    visibility = repository.get_quiz_visibility(quiz_id) or {}
    ensure_read_allowed(
        principal_from_request(request),
        ResourceVisibility(
            exists=True,
            guest_public=bool(quiz.guest_public),
            owner_user_id=visibility.get("owner_user_id"),
            not_found_detail="Quiz not found",
        ),
    )
    return _rehydrate_related_word_pack_links(repository, quiz)


@router.post(
    "/{quiz_id}/guest-public",
    response_model=QuizGuestPublicUpdateResponse,
    summary="Quizのゲスト公開フラグを更新",
)
async def update_quiz_guest_public(
    quiz_id: str,
    req: QuizGuestPublicUpdateRequest,
    principal: Principal = Depends(require_user_permission(Permission.QUIZ_UPDATE)),
) -> QuizGuestPublicUpdateResponse:
    repository = get_store()
    visibility = repository.get_quiz_visibility(quiz_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="Quiz not found",
    )
    updated = repository.update_quiz_guest_public(quiz_id, req.guest_public)
    if updated is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return QuizGuestPublicUpdateResponse(quiz_id=quiz_id, guest_public=updated)


@router.delete(
    "/{quiz_id}",
    summary="Quizを削除",
)
async def delete_quiz(
    quiz_id: str,
    principal: Principal = Depends(require_user_permission(Permission.QUIZ_DELETE)),
) -> dict[str, str]:
    repository = get_store()
    visibility = repository.get_quiz_visibility(quiz_id)
    if visibility is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    ensure_user_write_allowed(
        principal,
        owner_user_id=visibility.get("owner_user_id"),
        not_found_detail="Quiz not found",
    )
    success = repository.delete_quiz(quiz_id)
    if not success:
        raise HTTPException(status_code=404, detail="Quiz not found")
    return {"message": "Quiz deleted successfully"}


@router.post(
    "/{quiz_id}/attempts",
    response_model=QuizAttemptResponse,
    summary="Quizを採点してAttemptを保存",
)
async def submit_quiz_attempt(
    quiz_id: str,
    req: QuizAttemptRequest,
    principal: Principal = Depends(require_user_permission(Permission.QUIZ_ATTEMPT_WRITE)),
) -> QuizAttemptResponse:
    row = get_store().get_quiz(quiz_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    quiz = Quiz.model_validate(row)
    score, total, results = score_quiz_attempt(quiz, req.answers)
    submitted_at = SystemClock().now_iso()
    percentage = (score / total * 100.0) if total else 0.0
    attempt_id = PrefixedUuidGenerator("quiz-attempt:").new_id()
    response = QuizAttemptResponse(
        id=attempt_id,
        quiz_id=quiz_id,
        score=score,
        total=total,
        percentage=percentage,
        results=results,
        started_at=req.started_at,
        submitted_at=submitted_at,
        elapsed_ms=req.elapsed_ms,
    )
    get_store().save_quiz_attempt(
        attempt_id,
        {
            "quiz_id": quiz_id,
            "answers": [answer.model_dump(mode="json") for answer in req.answers],
            "score": score,
            "total": total,
            "percentage": percentage,
            "results": [result.model_dump(mode="json") for result in results],
            "started_at": req.started_at,
            "submitted_at": submitted_at,
            "elapsed_ms": req.elapsed_ms,
            "owner_user_id": principal.user_id,
            "created_at": submitted_at,
        },
    )
    return response


@router.get(
    "/{quiz_id}/attempts",
    response_model=list[QuizAttemptResponse],
    summary="QuizのAttempt履歴を取得",
)
async def list_quiz_attempts(
    quiz_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _principal: Principal = Depends(require_user_permission(Permission.QUIZ_READ)),
) -> list[QuizAttemptResponse]:
    if get_store().get_quiz(quiz_id) is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    rows = get_store().list_quiz_attempts(quiz_id, limit=limit, offset=offset)
    return [QuizAttemptResponse.model_validate(row) for row in rows]
