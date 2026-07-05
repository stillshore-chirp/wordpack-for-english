from __future__ import annotations

from typing import Literal

from .base import Any, FirestoreBaseRepository, Mapping, firestore, json

QuizGenerationJobStatus = Literal["queued", "running", "succeeded", "failed"]


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(raw: Any, fallback: Any) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return fallback
    return raw


class FirestoreQuizRepository(FirestoreBaseRepository):
    """Quiz 本体、関連 WordPack link、Attempt を Firestore で管理する。"""

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._quizzes = client.collection("quizzes")
        self._quiz_word_packs = client.collection("quiz_word_packs")
        self._quiz_attempts = client.collection("quiz_attempts")
        self._quiz_generation_jobs = client.collection("quiz_generation_jobs")

    def save_quiz(
        self,
        quiz_id: str,
        payload: Mapping[str, Any],
        related_word_packs: list[Mapping[str, Any]],
    ) -> None:
        now = self._now_iso()
        doc_ref = self._quizzes.document(quiz_id)
        existing = doc_ref.get()
        stored = existing.to_dict() if existing.exists else {}
        passages = list(payload.get("passages") or [])
        sections = list(payload.get("sections") or [])
        related = list(payload.get("related_word_packs") or [])
        doc_payload: dict[str, Any] = {
            "title_en": payload.get("title_en"),
            "format_profile": payload.get("format_profile"),
            "generation_domain": payload.get("generation_domain"),
            "domain_intensity": payload.get("domain_intensity"),
            "difficulty": payload.get("difficulty"),
            "passages_json": _json_dump(passages),
            "notes_ja": payload.get("notes_ja"),
            "sections_json": _json_dump(sections),
            "related_word_packs_json": _json_dump(related),
            "source_word_pack_ids": list(payload.get("source_word_pack_ids") or []),
            "source_lemmas": list(payload.get("source_lemmas") or []),
            "topic_seed": payload.get("topic_seed"),
            "avoid_topics": list(payload.get("avoid_topics") or []),
            "llm_model": payload.get("llm_model"),
            "llm_params": payload.get("llm_params"),
            "generation_started_at": payload.get("generation_started_at"),
            "generation_completed_at": payload.get("generation_completed_at"),
            "generation_duration_ms": payload.get("generation_duration_ms"),
            "guest_public": bool(payload.get("guest_public", False)),
            "owner_user_id": payload.get("owner_user_id", stored.get("owner_user_id")),
            "created_at": payload.get("created_at") or stored.get("created_at") or now,
            "updated_at": payload.get("updated_at") or now,
        }
        doc_ref.set(doc_payload, merge=True)
        for snapshot in list(self._quiz_word_packs.stream()):
            data = snapshot.to_dict() or {}
            if data.get("quiz_id") == quiz_id:
                snapshot.reference.delete()
        for link in related_word_packs:
            word_pack_id = str(link.get("word_pack_id") or "").strip()
            lemma = str(link.get("lemma") or "").strip()
            link_key = word_pack_id or f"lemma:{lemma.lower()}"
            safe_link_key = link_key.replace("/", "_")
            self._quiz_word_packs.document(f"{quiz_id}:{safe_link_key}").set(
                {
                    "quiz_id": quiz_id,
                    "word_pack_id": word_pack_id or None,
                    "lemma": lemma,
                    "status": link.get("status"),
                    "is_empty": bool(link.get("is_empty", False)),
                    "occurrences": list(link.get("occurrences") or []),
                    "warning": link.get("warning"),
                    "created_at": now,
                }
            )

    def _hydrate_quiz(self, quiz_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": quiz_id,
            "title_en": str(data.get("title_en") or ""),
            "format_profile": data.get("format_profile"),
            "generation_domain": data.get("generation_domain"),
            "domain_intensity": data.get("domain_intensity"),
            "difficulty": data.get("difficulty"),
            "passages": _json_load(data.get("passages_json"), []),
            "notes_ja": data.get("notes_ja"),
            "sections": _json_load(data.get("sections_json"), []),
            "related_word_packs": _json_load(data.get("related_word_packs_json"), []),
            "source_word_pack_ids": list(data.get("source_word_pack_ids") or []),
            "source_lemmas": list(data.get("source_lemmas") or []),
            "topic_seed": data.get("topic_seed"),
            "avoid_topics": list(data.get("avoid_topics") or []),
            "llm_model": data.get("llm_model"),
            "llm_params": data.get("llm_params"),
            "generation_started_at": data.get("generation_started_at"),
            "generation_completed_at": data.get("generation_completed_at"),
            "generation_duration_ms": data.get("generation_duration_ms"),
            "guest_public": bool(data.get("guest_public", False)),
            "owner_user_id": data.get("owner_user_id"),
            "created_at": str(data.get("created_at") or ""),
            "updated_at": str(data.get("updated_at") or ""),
        }

    def get_quiz(self, quiz_id: str) -> dict[str, Any] | None:
        doc = self._quizzes.document(quiz_id).get()
        if not doc.exists:
            return None
        return self._hydrate_quiz(doc.id, doc.to_dict() or {})

    def list_quizzes(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        public_only: bool = False,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        docs = list(self._quizzes.stream())
        if public_only:
            docs = [doc for doc in docs if bool((doc.to_dict() or {}).get("guest_public", False))]
        elif owner_user_id is not None:
            docs = [
                doc
                for doc in docs
                if str((doc.to_dict() or {}).get("owner_user_id") or "") == owner_user_id
            ]
        docs.sort(key=lambda d: str((d.to_dict() or {}).get("created_at") or ""), reverse=True)
        sliced = docs[max(0, offset) : max(0, offset) + max(0, limit)]
        return [self._hydrate_quiz(doc.id, doc.to_dict() or {}) for doc in sliced]

    def count_quizzes(self, *, public_only: bool = False, owner_user_id: str | None = None) -> int:
        if public_only:
            return sum(
                1
                for snapshot in self._quizzes.stream()
                if bool((snapshot.to_dict() or {}).get("guest_public", False))
            )
        if owner_user_id is not None:
            return sum(
                1
                for snapshot in self._quizzes.stream()
                if str((snapshot.to_dict() or {}).get("owner_user_id") or "") == owner_user_id
            )
        return sum(
            1 for _ in self._quizzes.stream()
        )

    def delete_quiz(self, quiz_id: str) -> bool:
        doc_ref = self._quizzes.document(quiz_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        doc_ref.delete()
        for collection in (self._quiz_word_packs, self._quiz_attempts):
            for link in list(collection.stream()):
                data = link.to_dict() or {}
                if data.get("quiz_id") == quiz_id:
                    link.reference.delete()
        return True

    def update_quiz_guest_public(self, quiz_id: str, guest_public: bool) -> bool | None:
        doc_ref = self._quizzes.document(quiz_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        value = bool(guest_public)
        doc_ref.update({"guest_public": value, "updated_at": self._now_iso()})
        return value

    def get_quiz_visibility(self, quiz_id: str) -> dict[str, Any] | None:
        doc = self._quizzes.document(quiz_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        owner_raw = data.get("owner_user_id")
        return {
            "guest_public": bool(data.get("guest_public", False)),
            "owner_user_id": str(owner_raw).strip() if owner_raw else None,
        }

    def save_quiz_attempt(self, attempt_id: str, payload: Mapping[str, Any]) -> None:
        now = self._now_iso()
        self._quiz_attempts.document(attempt_id).set(
            {
                "quiz_id": payload.get("quiz_id"),
                "answers_json": _json_dump(list(payload.get("answers") or [])),
                "results_json": _json_dump(list(payload.get("results") or [])),
                "score": int(payload.get("score") or 0),
                "total": int(payload.get("total") or 0),
                "percentage": float(payload.get("percentage") or 0.0),
                "started_at": payload.get("started_at"),
                "submitted_at": payload.get("submitted_at") or now,
                "elapsed_ms": payload.get("elapsed_ms"),
                "owner_user_id": payload.get("owner_user_id"),
                "created_at": payload.get("created_at") or now,
            }
        )

    def get_quiz_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        doc = self._quiz_attempts.document(attempt_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return {
            "id": doc.id,
            "quiz_id": str(data.get("quiz_id") or ""),
            "score": int(data.get("score") or 0),
            "total": int(data.get("total") or 0),
            "percentage": float(data.get("percentage") or 0.0),
            "results": _json_load(data.get("results_json"), []),
            "started_at": data.get("started_at"),
            "submitted_at": str(data.get("submitted_at") or ""),
            "elapsed_ms": data.get("elapsed_ms"),
        }

    def list_quiz_attempts(
        self,
        quiz_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows: list[tuple[str, Mapping[str, Any]]] = []
        for snapshot in self._quiz_attempts.stream():
            data = snapshot.to_dict() or {}
            if data.get("quiz_id") == quiz_id:
                rows.append((snapshot.id, data))
        rows.sort(key=lambda row: str(row[1].get("submitted_at") or ""), reverse=True)
        sliced = rows[max(0, offset) : max(0, offset) + max(0, limit)]
        return [
            {
                "id": attempt_id,
                "quiz_id": str(data.get("quiz_id") or ""),
                "score": int(data.get("score") or 0),
                "total": int(data.get("total") or 0),
                "percentage": float(data.get("percentage") or 0.0),
                "results": _json_load(data.get("results_json"), []),
                "started_at": data.get("started_at"),
                "submitted_at": str(data.get("submitted_at") or ""),
                "elapsed_ms": data.get("elapsed_ms"),
            }
            for attempt_id, data in sliced
        ]

    def create_quiz_generation_job(
        self,
        *,
        job_id: str,
        status: QuizGenerationJobStatus = "queued",
    ) -> Mapping[str, Any]:
        now = self._now_iso()
        payload: dict[str, Any] = {
            "job_id": job_id,
            "status": status,
            "quiz_id": None,
            "result_json": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        self._quiz_generation_jobs.document(job_id).set(payload)
        return payload

    def update_quiz_generation_job(
        self,
        job_id: str,
        *,
        status: QuizGenerationJobStatus,
        quiz_id: str | None = None,
        result_json: str | None = None,
        error: str | None = None,
    ) -> Mapping[str, Any] | None:
        doc_ref = self._quiz_generation_jobs.document(job_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        updates: dict[str, Any] = {
            "status": status,
            "updated_at": self._now_iso(),
        }
        if quiz_id is not None:
            updates["quiz_id"] = quiz_id
        if result_json is not None:
            updates["result_json"] = result_json
        if status == "failed":
            updates["error"] = error or "Quiz generation job failed"
        elif error is not None:
            updates["error"] = error
        doc_ref.update(updates)
        updated = doc_ref.get()
        return updated.to_dict() or None

    def get_quiz_generation_job(self, job_id: str) -> Mapping[str, Any] | None:
        snapshot = self._quiz_generation_jobs.document(job_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict() or None


FirestoreQuizStore = FirestoreQuizRepository

__all__ = ["FirestoreQuizRepository", "FirestoreQuizStore", "QuizGenerationJobStatus"]
