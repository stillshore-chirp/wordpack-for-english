from __future__ import annotations

import asyncio
from typing import Any

from backend.application.quiz import generation_jobs
from backend.domain.quiz.generation_progress import QuizGenerationProgress
from backend.models.quiz import Quiz, QuizGenerateRequest


def _quiz_payload() -> dict[str, Any]:
    return {
        "id": "quiz:persistent",
        "title_en": "Persistent Quiz",
        "format_profile": "single_passage",
        "generation_domain": "technical",
        "domain_intensity": "standard",
        "difficulty": "medium",
        "passages": [
            {
                "id": "p1",
                "order": 1,
                "kind": "article",
                "title": "Persistence",
                "body_en": "Latency is reviewed before release.",
                "body_ja": None,
                "speaker_labels": [],
            }
        ],
        "notes_ja": None,
        "sections": [
            {
                "id": "s1",
                "order": 1,
                "title": "Reading",
                "description_ja": None,
                "passage_ids": ["p1"],
                "questions": [
                    {
                        "id": "q1",
                        "order": 1,
                        "type": "detail",
                        "prompt": "What is reviewed?",
                        "choices": [
                            {"id": "A", "text": "Latency"},
                            {"id": "B", "text": "Hiring"},
                            {"id": "C", "text": "Travel"},
                            {"id": "D", "text": "Meals"},
                        ],
                        "correct_choice_id": "A",
                        "explanation": {
                            "explanation_ja": "本文に latency とあります。",
                            "evidence_passage_id": "p1",
                            "evidence_text": "Latency is reviewed",
                            "evidence_start": 0,
                            "evidence_end": 19,
                            "wrong_choice_explanations_ja": {},
                            "related_lemmas": ["latency"],
                        },
                    }
                ],
            }
        ],
        "related_word_packs": [],
        "source_word_pack_ids": [],
        "source_lemmas": ["latency"],
        "topic_seed": None,
        "avoid_topics": [],
        "llm_model": None,
        "llm_params": None,
        "guest_public": False,
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }


class PersistentJobStore:
    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}

    def create_quiz_generation_job(self, *, job_id: str, status: str = "queued") -> dict[str, Any]:
        record = {
            "job_id": job_id,
            "status": status,
            "quiz_id": None,
            "result_json": None,
            "error": None,
            "error_code": None,
            "attempt_count": 0,
            "attempt_limit": 5,
            "retry_phase": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }
        self.records[job_id] = record
        return dict(record)

    def update_quiz_generation_job(
        self,
        job_id: str,
        *,
        status: str,
        quiz_id: str | None = None,
        result_json: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
        attempt_count: int | None = None,
        attempt_limit: int | None = None,
        retry_phase: str | None = None,
    ) -> dict[str, Any] | None:
        record = self.records.get(job_id)
        if record is None:
            return None
        record["status"] = status
        record["updated_at"] = "2024-01-01T00:00:01+00:00"
        if quiz_id is not None:
            record["quiz_id"] = quiz_id
        if result_json is not None:
            record["result_json"] = result_json
        if error is not None:
            record["error"] = error
        if error_code is not None:
            record["error_code"] = error_code
        if attempt_count is not None:
            record["attempt_count"] = attempt_count
        if attempt_limit is not None:
            record["attempt_limit"] = attempt_limit
        if retry_phase is not None:
            record["retry_phase"] = retry_phase
        return dict(record)

    def get_quiz_generation_job(self, job_id: str) -> dict[str, Any] | None:
        record = self.records.get(job_id)
        return dict(record) if record is not None else None


class FakeQuizGenerator:
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress=None,
    ) -> Quiz:
        return Quiz.model_validate(_quiz_payload())


class ProgressQuizGenerator(FakeQuizGenerator):
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress=None,
    ) -> Quiz:
        assert on_progress is not None
        await asyncio.to_thread(
            on_progress,
            QuizGenerationProgress(
                attempt_count=3,
                attempt_limit=5,
                retry_phase="translation_alignment",
            ),
        )
        return await super().generate(req, store, on_progress=on_progress)


class FailedAlignmentQuizGenerator:
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress=None,
    ) -> Quiz:
        assert on_progress is not None
        await asyncio.to_thread(
            on_progress,
            QuizGenerationProgress(
                attempt_count=5,
                attempt_limit=5,
                retry_phase="translation_alignment",
            ),
        )
        raise RuntimeError("QUIZ_TRANSLATION_ALIGNMENT_FAILED")


class FailedJsonQuizGenerator:
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress=None,
    ) -> Quiz:
        raise RuntimeError("QUIZ_JSON_PARSE_FAILED")


class SensitiveFailureQuizGenerator:
    async def generate(
        self,
        req: QuizGenerateRequest,
        store: object,
        *,
        on_progress=None,
    ) -> Quiz:
        raise RuntimeError("private generated passage must not be persisted")


class FakeClock:
    def now_iso(self) -> str:
        return "2024-01-01T00:00:00+00:00"


class FakeIdGenerator:
    def new_id(self) -> str:
        return "quiz-job:persistent"


def test_quiz_generation_job_status_reads_persistent_store() -> None:
    async def scenario() -> None:
        store = PersistentJobStore()

        req = QuizGenerateRequest.model_validate({"lemmas": ["latency"]})
        enqueued = await generation_jobs.enqueue_quiz_generation_job(
            req,
            store,
            generator=FakeQuizGenerator(),
            scheduler=None,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(),
        )
        generation_jobs._quiz_generation_jobs.clear()

        status = None
        for _ in range(20):
            status = await generation_jobs.get_quiz_generation_job(
                enqueued.job_id, store, clock=FakeClock()
            )
            if status is not None and status.status == "succeeded":
                break
            await asyncio.sleep(0.01)

        assert status is not None
        assert status.status == "succeeded"
        assert status.quiz_id == "quiz:persistent"
        assert status.result is not None
        assert status.result.title_en == "Persistent Quiz"

    asyncio.run(scenario())


def test_quiz_generation_job_persists_retry_progress_after_completion() -> None:
    async def scenario() -> None:
        store = PersistentJobStore()
        req = QuizGenerateRequest.model_validate({"lemmas": ["latency"]})

        enqueued = await generation_jobs.enqueue_quiz_generation_job(
            req,
            store,
            generator=ProgressQuizGenerator(),
            scheduler=None,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(),
        )

        status = await generation_jobs.get_quiz_generation_job(
            enqueued.job_id,
            store,
            clock=FakeClock(),
        )
        assert status is not None
        assert status.status == "succeeded"
        assert status.attempt_count == 3
        assert status.attempt_limit == 5
        assert status.retry_phase == "translation_alignment"
        stored = store.records[status.job_id]
        assert stored["attempt_count"] == 3
        assert stored["retry_phase"] == "translation_alignment"

    asyncio.run(scenario())


def test_quiz_generation_job_returns_safe_alignment_failure_message() -> None:
    async def scenario() -> None:
        store = PersistentJobStore()
        req = QuizGenerateRequest.model_validate({"lemmas": ["latency"]})

        enqueued = await generation_jobs.enqueue_quiz_generation_job(
            req,
            store,
            generator=FailedAlignmentQuizGenerator(),
            scheduler=None,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(),
        )

        status = await generation_jobs.get_quiz_generation_job(
            enqueued.job_id,
            store,
            clock=FakeClock(),
        )
        assert status is not None
        assert status.status == "failed"
        assert status.error_code == "QUIZ_TRANSLATION_ALIGNMENT_FAILED"
        assert status.error == (
            "英文と日本語訳の文対応を確認できなかったため、5回試行後にQuiz生成を停止しました。"
            "時間をおいてもう一度生成してください。"
        )
        assert status.attempt_count == 5

    asyncio.run(scenario())


def test_quiz_generation_job_returns_safe_json_failure_message() -> None:
    async def scenario() -> None:
        store = PersistentJobStore()
        req = QuizGenerateRequest.model_validate({"lemmas": ["latency"]})

        enqueued = await generation_jobs.enqueue_quiz_generation_job(
            req,
            store,
            generator=FailedJsonQuizGenerator(),
            scheduler=None,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(),
        )
        status = await generation_jobs.get_quiz_generation_job(
            enqueued.job_id,
            store,
            clock=FakeClock(),
        )

        assert status is not None
        assert status.status == "failed"
        assert status.error_code == "QUIZ_JSON_PARSE_FAILED"
        assert status.error == "生成結果の形式を確認できなかったため、Quiz生成を停止しました。"

    asyncio.run(scenario())


def test_quiz_generation_job_does_not_persist_or_return_unknown_exception_text() -> None:
    async def scenario() -> None:
        store = PersistentJobStore()
        req = QuizGenerateRequest.model_validate({"lemmas": ["latency"]})

        enqueued = await generation_jobs.enqueue_quiz_generation_job(
            req,
            store,
            generator=SensitiveFailureQuizGenerator(),
            scheduler=None,
            id_generator=FakeIdGenerator(),
            clock=FakeClock(),
        )
        status = await generation_jobs.get_quiz_generation_job(
            enqueued.job_id,
            store,
            clock=FakeClock(),
        )

        assert status is not None
        assert status.status == "failed"
        assert status.error_code is None
        assert status.error == (
            "Quiz生成を完了できませんでした。時間をおいてもう一度生成してください。"
        )
        assert "private generated passage" not in str(store.records[enqueued.job_id])

    asyncio.run(scenario())
