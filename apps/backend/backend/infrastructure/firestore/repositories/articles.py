from __future__ import annotations

from .base import Any, firestore
from .base import FirestoreBaseRepository


class FirestoreArticleRepository(FirestoreBaseRepository):
    """記事と WordPack リンクを Firestore で管理する。"""

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._articles = client.collection("articles")
        self._article_word_packs = client.collection("article_word_packs")

    def save_article(
        self,
        article_id: str,
        **kwargs: Any,
    ) -> None:
        now = self._now_iso()
        related_word_packs = kwargs.pop("related_word_packs", None)
        created_at = kwargs.pop("created_at", None)
        updated_at = kwargs.pop("updated_at", None)
        generation_started_at = kwargs.pop("generation_started_at", None)
        generation_completed_at = kwargs.pop("generation_completed_at", None)
        generation_duration_ms = kwargs.pop("generation_duration_ms", None)
        doc_ref = self._articles.document(article_id)
        existing = doc_ref.get()
        stored = existing.to_dict() if existing.exists else {}
        payload = {
            "title_en": kwargs.get("title_en"),
            "body_en": kwargs.get("body_en"),
            "body_ja": kwargs.get("body_ja"),
            "notes_ja": kwargs.get("notes_ja"),
            "llm_model": kwargs.get("llm_model"),
            "llm_params": kwargs.get("llm_params"),
            "generation_category": kwargs.get("generation_category"),
            "created_at": created_at or stored.get("created_at") or now,
            "updated_at": updated_at or now,
            "generation_started_at": generation_started_at or stored.get("generation_started_at") or created_at or now,
            "generation_completed_at": generation_completed_at or stored.get("generation_completed_at") or updated_at or now,
            "generation_duration_ms": (
                int(generation_duration_ms)
                if generation_duration_ms is not None
                else stored.get("generation_duration_ms")
            ),
            "guest_public": bool(kwargs.get("guest_public", stored.get("guest_public", False))),
            "owner_user_id": kwargs.get("owner_user_id", stored.get("owner_user_id")),
        }
        doc_ref.set(payload, merge=True)
        if related_word_packs is not None:
            for snapshot in list(self._article_word_packs.stream()):
                data = snapshot.to_dict() or {}
                if data.get("article_id") == article_id:
                    snapshot.reference.delete()
            for wp_id, lemma, status in related_word_packs:
                link_id = f"{article_id}:{wp_id}"
                self._article_word_packs.document(link_id).set(
                    {
                        "article_id": article_id,
                        "word_pack_id": wp_id,
                        "lemma": lemma,
                        "status": status,
                        "created_at": now,
                    }
                )

    def get_article(
        self,
        article_id: str,
    ) -> tuple[
        str,
        str,
        str,
        str | None,
        str | None,
        str | None,
        str | None,
        str,
        str,
        str | None,
        str | None,
        int | None,
        bool,
        list[tuple[str, str, str]],
    ] | None:
        doc = self._articles.document(article_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        related: list[tuple[str, str, str]] = []
        for snapshot in self._article_word_packs.stream():
            link = snapshot.to_dict() or {}
            if link.get("article_id") != article_id:
                continue
            related.append(
                (
                    str(link.get("word_pack_id") or ""),
                    str(link.get("lemma") or ""),
                    str(link.get("status") or ""),
                )
            )
        return (
            str(data.get("title_en") or ""),
            str(data.get("body_en") or ""),
            str(data.get("body_ja") or ""),
            data.get("notes_ja"),
            data.get("llm_model"),
            data.get("llm_params"),
            data.get("generation_category"),
            str(data.get("created_at") or ""),
            str(data.get("updated_at") or ""),
            data.get("generation_started_at"),
            data.get("generation_completed_at"),
            data.get("generation_duration_ms"),
            bool(data.get("guest_public", False)),
            related,
        )

    def list_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        public_only: bool = False,
        owner_user_id: str | None = None,
    ) -> list[tuple[str, str, str, str, bool]]:
        query = self._articles
        if public_only:
            query = query.where("guest_public", "==", True)
        elif owner_user_id is not None:
            query = query.where("owner_user_id", "==", owner_user_id)
        docs = list(query.stream())
        docs.sort(key=lambda d: str((d.to_dict() or {}).get("created_at") or ""), reverse=True)
        sliced = docs[offset : offset + limit]
        return [
            (
                doc.id,
                str((doc.to_dict() or {}).get("title_en") or ""),
                str((doc.to_dict() or {}).get("created_at") or ""),
                str((doc.to_dict() or {}).get("updated_at") or ""),
                bool((doc.to_dict() or {}).get("guest_public", False)),
            )
            for doc in sliced
        ]

    def count_articles(
        self, *, public_only: bool = False, owner_user_id: str | None = None
    ) -> int:
        query = self._articles
        if public_only:
            query = query.where("guest_public", "==", True)
        elif owner_user_id is not None:
            query = query.where("owner_user_id", "==", owner_user_id)
        return sum(1 for _ in query.stream())

    def update_article_guest_public(self, article_id: str, guest_public: bool) -> bool | None:
        doc_ref = self._articles.document(article_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        value = bool(guest_public)
        doc_ref.update({"guest_public": value, "updated_at": self._now_iso()})
        return value

    def delete_article(self, article_id: str) -> bool:
        doc_ref = self._articles.document(article_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        doc_ref.delete()
        for link in list(self._article_word_packs.stream()):
            data = link.to_dict() or {}
            if data.get("article_id") == article_id:
                link.reference.delete()
        return True

    def get_article_visibility(self, article_id: str) -> dict[str, Any] | None:
        doc = self._articles.document(article_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        owner_raw = data.get("owner_user_id")
        return {
            "guest_public": bool(data.get("guest_public", False)),
            "owner_user_id": str(owner_raw).strip() if owner_raw else None,
        }


FirestoreArticleStore = FirestoreArticleRepository

__all__ = ["FirestoreArticleRepository", "FirestoreArticleStore"]
