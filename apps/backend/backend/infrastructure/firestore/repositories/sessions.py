from __future__ import annotations

from .base import Any, FirestoreBaseRepository, Mapping, firestore


class FirestoreSessionRepository(FirestoreBaseRepository):
    """Server-side session records backing signed opaque cookie tokens."""

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._sessions = client.collection("sessions")

    def create_session(self, payload: Mapping[str, Any]) -> None:
        sid = str(payload.get("sid") or "").strip()
        if not sid:
            raise ValueError("sid is required")
        self._sessions.document(sid).set(dict(payload))

    def get_session(self, sid: str) -> Mapping[str, Any] | None:
        snapshot = self._sessions.document(str(sid)).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict() or {}

    def revoke_session(self, sid: str, *, revoked_at: str) -> bool:
        doc_ref = self._sessions.document(str(sid))
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        doc_ref.update({"revoked_at": revoked_at, "updated_at": revoked_at})
        return True

    def touch_session(self, sid: str, *, last_seen_at: str) -> bool:
        doc_ref = self._sessions.document(str(sid))
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        doc_ref.update({"last_seen_at": last_seen_at, "updated_at": last_seen_at})
        return True


FirestoreSessionStore = FirestoreSessionRepository

__all__ = ["FirestoreSessionRepository", "FirestoreSessionStore"]
