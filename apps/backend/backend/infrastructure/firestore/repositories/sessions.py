from __future__ import annotations

from .base import AlreadyExists, Any, FirestoreBaseRepository, Mapping, firestore


class FirestoreSessionRepository(FirestoreBaseRepository):
    """Server-side session records backing signed opaque cookie tokens."""

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._sessions = client.collection("sessions")
        self._session_revocations = client.collection("session_revocations")

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

    def get_session_revocation(self, token_digest: str) -> Mapping[str, Any] | None:
        """Read a legacy-token revocation tombstone by its opaque digest."""

        digest = str(token_digest).strip()
        if not digest:
            return None
        snapshot = self._session_revocations.document(digest).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict() or {}

    def create_session_revocation(
        self,
        token_digest: str,
        *,
        kind: str,
        revoked_at: str,
    ) -> bool:
        """Create a legacy-token tombstone without overwriting an existing document."""

        digest = str(token_digest).strip()
        if not digest:
            raise ValueError("token_digest is required")
        if kind not in {"user", "guest"}:
            raise ValueError("session revocation kind is invalid")

        doc_ref = self._session_revocations.document(digest)
        payload = {
            "kind": kind,
            "revoked_at": revoked_at,
            "updated_at": revoked_at,
        }
        try:
            # Firestore create is atomic and fails if another request already
            # wrote this digest.  This prevents a legacy token from replacing
            # an active session or another token's tombstone.
            doc_ref.create(payload)
        except AlreadyExists:
            snapshot = doc_ref.get()
            existing = snapshot.to_dict() if snapshot.exists else None
            return bool(
                isinstance(existing, Mapping)
                and existing.get("kind") == kind
                and existing.get("revoked_at")
            )
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
