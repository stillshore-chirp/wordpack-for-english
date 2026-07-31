from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from .base import AlreadyExists, FirestoreBaseRepository, firestore

GenerationJobStatus = Literal["queued", "running", "succeeded", "failed"]


class FirestoreGenerationJobRepository(FirestoreBaseRepository):
    """長時間かかる生成操作の状態と結果を revision を跨いで保持する。"""

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._jobs = client.collection("generation_jobs")

    def create_generation_job(
        self,
        *,
        job_id: str,
        owner_user_id: str,
        job_type: str,
        status: GenerationJobStatus = "queued",
    ) -> Mapping[str, Any]:
        now = self._now_iso()
        payload: dict[str, Any] = {
            "job_id": job_id,
            "owner_user_id": owner_user_id,
            "job_type": job_type,
            "status": status,
            "result_json": None,
            "error": None,
            "created_at": now,
            "updated_at": now,
        }
        doc_ref = self._jobs.document(job_id)
        try:
            doc_ref.create(payload)
            return {**payload, "_created": True}
        except AlreadyExists:
            snapshot = doc_ref.get()
            existing = snapshot.to_dict() if snapshot.exists else None
            if existing is None:
                raise
            return {**existing, "_created": False}

    def update_generation_job(
        self,
        job_id: str,
        *,
        status: GenerationJobStatus,
        result_json: str | None = None,
        error: str | None = None,
    ) -> Mapping[str, Any] | None:
        doc_ref = self._jobs.document(job_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        updates: dict[str, Any] = {
            "status": status,
            "updated_at": self._now_iso(),
        }
        if result_json is not None:
            updates["result_json"] = result_json
        if status == "failed":
            updates["error"] = error or "生成ジョブが失敗しました"
        elif error is not None:
            updates["error"] = error
        doc_ref.update(updates)
        updated = doc_ref.get()
        return updated.to_dict() or None

    def get_generation_job(self, job_id: str) -> Mapping[str, Any] | None:
        snapshot = self._jobs.document(job_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict() or None


FirestoreGenerationJobStore = FirestoreGenerationJobRepository
