from __future__ import annotations

import asyncio
from typing import Any

from backend.application.quiz import generation_jobs
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
        return dict(record)

    def get_quiz_generation_job(self, job_id: str) -> dict[str, Any] | None:
        record = self.records.get(job_id)
        return dict(record) if record is not None else None


class FakeQuizGenerator:
    async def generate(self, req: QuizGenerateRequest, store: object) -> Quiz:
        return Quiz.model_validate(_quiz_payload())


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
