from __future__ import annotations

from .base import Any, Iterable, Mapping, Sequence, datetime, firestore
from .articles import FirestoreArticleRepository
from .examples import FirestoreExampleRepository
from .quizzes import FirestoreQuizRepository, QuizGenerationJobStatus
from .regenerate_jobs import FirestoreRegenerateJobRepository, RegenerateJobStatus
from .sessions import FirestoreSessionRepository
from .users import FirestoreUserRepository
from .wordpacks import FirestoreWordPackRepository


class AppFirestoreRepository:
    """Firestore concrete repository を束ねる application persistence adapter。"""

    user_repository_cls = FirestoreUserRepository
    wordpack_repository_cls = FirestoreWordPackRepository
    example_repository_cls = FirestoreExampleRepository
    article_repository_cls = FirestoreArticleRepository
    quiz_repository_cls = FirestoreQuizRepository
    regenerate_job_repository_cls = FirestoreRegenerateJobRepository
    session_repository_cls = FirestoreSessionRepository

    def __init__(self, *, client: firestore.Client | None = None) -> None:
        self._client = client or firestore.Client()
        self.users = self.user_repository_cls(self._client)
        self.wordpacks = self.wordpack_repository_cls(self._client)
        self.examples = self.example_repository_cls(self._client, self.wordpacks)
        self.articles = self.article_repository_cls(self._client)
        self.quizzes = self.quiz_repository_cls(self._client)
        self.regenerate_jobs = self.regenerate_job_repository_cls(self._client)
        self.sessions = self.session_repository_cls(self._client)

    # --- Users ---
    def record_user_login(
        self,
        *,
        google_sub: str,
        email: str,
        display_name: str,
        login_at: datetime | None = None,
    ) -> dict[str, str]:
        return self.users.record_user_login(
            google_sub=google_sub,
            email=email,
            display_name=display_name,
            login_at=login_at,
        )

    def get_user_by_google_sub(self, google_sub: str) -> dict[str, str] | None:
        return self.users.get_user_by_google_sub(google_sub)

    def delete_user(self, google_sub: str) -> None:
        self.users.delete_user(google_sub)

    # --- WordPacks ---
    def save_word_pack(
        self,
        word_pack_id: str,
        lemma: str,
        data: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.wordpacks.save_word_pack(word_pack_id, lemma, data, metadata=metadata)

    def get_word_pack(self, word_pack_id: str) -> tuple[str, str, str, str] | None:
        return self.wordpacks.get_word_pack(word_pack_id)

    def list_word_packs(self, limit: int = 50, offset: int = 0) -> list[tuple[str, str, str, str, str]]:
        return self.wordpacks.list_word_packs(limit=limit, offset=offset)

    def count_word_packs(self) -> int:
        return self.wordpacks.count_word_packs()

    def count_owned_word_packs(self, owner_user_id: str) -> int:
        return self.wordpacks.count_owned_word_packs(owner_user_id)

    def get_word_pack_metadata(self, word_pack_id: str) -> Mapping[str, Any] | None:
        return self.wordpacks.get_word_pack_metadata(word_pack_id)

    def has_guest_demo_word_pack(self) -> bool:
        return self.wordpacks.has_guest_demo_word_pack()

    def list_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_word_packs_with_flags(limit=limit, offset=offset)

    def list_all_word_packs_with_flags(
        self,
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_all_word_packs_with_flags()

    def list_public_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_public_word_packs_with_flags(limit=limit, offset=offset)

    def list_all_public_word_packs_with_flags(
        self,
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_all_public_word_packs_with_flags()

    def list_owned_word_packs_with_flags(
        self, owner_user_id: str, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_owned_word_packs_with_flags(
            owner_user_id, limit=limit, offset=offset
        )

    def list_all_owned_word_packs_with_flags(
        self, owner_user_id: str
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return self.wordpacks.list_all_owned_word_packs_with_flags(owner_user_id)

    def delete_word_pack(self, word_pack_id: str) -> bool:
        return self.wordpacks.delete_word_pack(word_pack_id)

    def update_word_pack_study_progress(
        self, word_pack_id: str, checked_increment: int, learned_increment: int
    ) -> tuple[int, int] | None:
        return self.wordpacks.update_word_pack_study_progress(
            word_pack_id, checked_increment, learned_increment
        )

    def find_word_pack_id_by_lemma(
        self, lemma: str, *, diagnostics: bool = False
    ) -> str | None | tuple[str | None, bool]:
        return self.wordpacks.find_word_pack_id_by_lemma(
            lemma, diagnostics=diagnostics
        )

    def find_word_pack_by_lemma_ci(self, lemma: str) -> tuple[str, str, str] | None:
        return self.wordpacks.find_word_pack_by_lemma_ci(lemma)

    def count_public_word_packs(self) -> int:
        return self.wordpacks.count_public_word_packs()

    def is_word_pack_guest_public(self, word_pack_id: str) -> bool:
        return self.wordpacks.is_word_pack_guest_public(word_pack_id)

    def update_word_pack_metadata(
        self,
        word_pack_id: str,
        *,
        updated_at: str | None = None,
        category_counts: Mapping[str, int] | None = None,
        guest_public: bool | None = None,
    ) -> None:
        return self.wordpacks.update_word_pack_metadata(
            word_pack_id,
            updated_at=updated_at,
            category_counts=category_counts,
            guest_public=guest_public,
        )

    def get_word_pack_visibility(self, word_pack_id: str) -> Mapping[str, Any] | None:
        return self.wordpacks.get_word_pack_visibility(word_pack_id)

    # --- Regenerate jobs ---
    def create_regenerate_job(
        self,
        *,
        job_id: str,
        word_pack_id: str,
        status: RegenerateJobStatus = "pending",
    ) -> Mapping[str, Any]:
        return self.regenerate_jobs.create_regenerate_job(
            job_id=job_id,
            word_pack_id=word_pack_id,
            status=status,
        )

    def update_regenerate_job(
        self,
        job_id: str,
        *,
        status: RegenerateJobStatus,
        error: str | None = None,
        result_json: str | None = None,
    ) -> Mapping[str, Any] | None:
        return self.regenerate_jobs.update_regenerate_job(
            job_id,
            status=status,
            error=error,
            result_json=result_json,
        )

    def get_regenerate_job(self, job_id: str) -> Mapping[str, Any] | None:
        return self.regenerate_jobs.get_regenerate_job(job_id)

    # --- Examples ---
    def update_example_study_progress(
        self, example_id: int, checked_increment: int, learned_increment: int
    ) -> tuple[str, int, int] | None:
        return self.examples.update_example_study_progress(
            example_id, checked_increment, learned_increment
        )

    def get_example_word_pack_id(self, example_id: int) -> str | None:
        return self.examples.get_example_word_pack_id(example_id)

    def delete_example(self, word_pack_id: str, category: str, index: int) -> int | None:
        return self.examples.delete_example(word_pack_id, category, index)

    def delete_examples_by_ids(
        self, example_ids: Iterable[int]
    ) -> tuple[int, list[int]]:
        return self.examples.delete_examples_by_ids(example_ids)

    def append_examples(
        self, word_pack_id: str, category: str, items: Sequence[Mapping[str, Any]]
    ) -> int:
        return self.examples.append_examples(word_pack_id, category, items)

    def count_examples(
        self,
        *,
        search: str | None = None,
        search_mode: str = "contains",
        category: str | None = None,
        public_only: bool = False,
    ) -> int:
        return self.examples.count_examples(
            search=search,
            search_mode=search_mode,
            category=category,
            public_only=public_only,
        )

    def list_examples(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "desc",
        search: str | None = None,
        search_mode: str = "contains",
        category: str | None = None,
        public_only: bool = False,
    ) -> list[
        tuple[int, str, str, str, str, str, str | None, str, str | None, int, int, int]
    ]:
        return self.examples.list_examples(
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
            search=search,
            search_mode=search_mode,
            category=category,
            public_only=public_only,
        )

    def update_example_transcription_typing(
        self, example_id: int, input_length: int
    ) -> int | None:
        return self.examples.update_example_transcription_typing(example_id, input_length)

    # --- Articles ---
    def save_article(self, article_id: str, **kwargs: Any) -> None:
        self.articles.save_article(article_id, **kwargs)

    def get_article(
        self, article_id: str
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
        return self.articles.get_article(article_id)

    def list_articles(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        public_only: bool = False,
        owner_user_id: str | None = None,
    ) -> list[tuple[str, str, str, str, bool]]:
        return self.articles.list_articles(
            limit=limit,
            offset=offset,
            public_only=public_only,
            owner_user_id=owner_user_id,
        )

    def count_articles(
        self, *, public_only: bool = False, owner_user_id: str | None = None
    ) -> int:
        return self.articles.count_articles(
            public_only=public_only,
            owner_user_id=owner_user_id,
        )

    def update_article_guest_public(self, article_id: str, guest_public: bool) -> bool | None:
        return self.articles.update_article_guest_public(article_id, guest_public)

    def delete_article(self, article_id: str) -> bool:
        return self.articles.delete_article(article_id)

    def get_article_visibility(self, article_id: str) -> Mapping[str, Any] | None:
        return self.articles.get_article_visibility(article_id)

    # --- Quizzes ---
    def save_quiz(
        self,
        quiz_id: str,
        payload: Mapping[str, Any],
        related_word_packs: list[Mapping[str, Any]],
    ) -> None:
        self.quizzes.save_quiz(quiz_id, payload, related_word_packs)

    def get_quiz(self, quiz_id: str) -> dict[str, Any] | None:
        return self.quizzes.get_quiz(quiz_id)

    def list_quizzes(
        self,
        limit: int = 50,
        offset: int = 0,
        *,
        public_only: bool = False,
        owner_user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.quizzes.list_quizzes(
            limit=limit,
            offset=offset,
            public_only=public_only,
            owner_user_id=owner_user_id,
        )

    def count_quizzes(
        self, *, public_only: bool = False, owner_user_id: str | None = None
    ) -> int:
        return self.quizzes.count_quizzes(
            public_only=public_only,
            owner_user_id=owner_user_id,
        )

    def delete_quiz(self, quiz_id: str) -> bool:
        return self.quizzes.delete_quiz(quiz_id)

    def update_quiz_guest_public(self, quiz_id: str, guest_public: bool) -> bool | None:
        return self.quizzes.update_quiz_guest_public(quiz_id, guest_public)

    def get_quiz_visibility(self, quiz_id: str) -> Mapping[str, Any] | None:
        return self.quizzes.get_quiz_visibility(quiz_id)

    def save_quiz_attempt(self, attempt_id: str, payload: Mapping[str, Any]) -> None:
        self.quizzes.save_quiz_attempt(attempt_id, payload)

    def get_quiz_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        return self.quizzes.get_quiz_attempt(attempt_id)

    def list_quiz_attempts(
        self,
        quiz_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self.quizzes.list_quiz_attempts(quiz_id, limit=limit, offset=offset)

    def create_quiz_generation_job(
        self,
        *,
        job_id: str,
        status: QuizGenerationJobStatus = "queued",
    ) -> Mapping[str, Any]:
        return self.quizzes.create_quiz_generation_job(
            job_id=job_id,
            status=status,
        )

    def update_quiz_generation_job(
        self,
        job_id: str,
        *,
        status: QuizGenerationJobStatus,
        quiz_id: str | None = None,
        result_json: str | None = None,
        error: str | None = None,
    ) -> Mapping[str, Any] | None:
        return self.quizzes.update_quiz_generation_job(
            job_id,
            status=status,
            quiz_id=quiz_id,
            result_json=result_json,
            error=error,
        )

    def get_quiz_generation_job(self, job_id: str) -> Mapping[str, Any] | None:
        return self.quizzes.get_quiz_generation_job(job_id)

    # --- Sessions ---
    def create_session(self, payload: Mapping[str, Any]) -> None:
        self.sessions.create_session(payload)

    def get_session(self, sid: str) -> Mapping[str, Any] | None:
        return self.sessions.get_session(sid)

    def revoke_session(self, sid: str, *, revoked_at: str) -> bool:
        return self.sessions.revoke_session(sid, revoked_at=revoked_at)

    def touch_session(self, sid: str, *, last_seen_at: str) -> bool:
        return self.sessions.touch_session(sid, last_seen_at=last_seen_at)


AppFirestoreStore = AppFirestoreRepository

__all__ = ["AppFirestoreRepository", "AppFirestoreStore"]
