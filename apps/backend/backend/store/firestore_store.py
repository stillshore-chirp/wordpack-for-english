from __future__ import annotations

from ..infrastructure.firestore.repositories.app_store import AppFirestoreRepository
from ..infrastructure.firestore.repositories.articles import FirestoreArticleRepository
from ..infrastructure.firestore.repositories.base import (
    FirestoreBaseRepository,
    _build_search_payload as _repository_build_search_payload,
    _coerce_firestore_snapshot as _repository_coerce_firestore_snapshot,
    _extract_count_from_aggregation as _repository_extract_count_from_aggregation,
    _extract_example_total as _repository_extract_example_total,
    _extract_search_terms as _repository_extract_search_terms,
    _normalize_search_text as _repository_normalize_search_text,
    _now_iso as _repository_now_iso,
    firestore,
)
from ..infrastructure.firestore.repositories.examples import FirestoreExampleRepository
from ..infrastructure.firestore.repositories.quizzes import FirestoreQuizRepository
from ..infrastructure.firestore.repositories.regenerate_jobs import FirestoreRegenerateJobRepository
from ..infrastructure.firestore.repositories.sessions import FirestoreSessionRepository
from ..infrastructure.firestore.repositories.users import FirestoreUserRepository
from ..infrastructure.firestore.repositories.wordpacks import FirestoreWordPackRepository


def _now_iso() -> str:
    return _repository_now_iso()


def _extract_count_from_aggregation(aggregation):
    return _repository_extract_count_from_aggregation(aggregation)


def _normalize_search_text(text):
    return _repository_normalize_search_text(text)


def _extract_search_terms(normalized_text):
    return _repository_extract_search_terms(normalized_text)


def _build_search_payload(en):
    return _repository_build_search_payload(en)


def _extract_example_total(metadata):
    return _repository_extract_example_total(metadata)


def _coerce_firestore_snapshot(candidate):
    return _repository_coerce_firestore_snapshot(candidate)


class _LegacyClockMixin:
    def _now_iso(self) -> str:
        return _now_iso()


FirestoreBaseStore = FirestoreBaseRepository


class FirestoreUserStore(_LegacyClockMixin, FirestoreUserRepository):
    """Legacy import path for the user repository."""


class FirestoreWordPackStore(_LegacyClockMixin, FirestoreWordPackRepository):
    """Legacy import path for the WordPack repository."""


class FirestoreExampleStore(_LegacyClockMixin, FirestoreExampleRepository):
    """Legacy import path for the example repository."""


class FirestoreArticleStore(_LegacyClockMixin, FirestoreArticleRepository):
    """Legacy import path for the article repository."""


class FirestoreQuizStore(_LegacyClockMixin, FirestoreQuizRepository):
    """Legacy import path for the quiz repository."""


class FirestoreRegenerateJobStore(_LegacyClockMixin, FirestoreRegenerateJobRepository):
    """Legacy import path for the regenerate job repository."""


class FirestoreSessionStore(FirestoreSessionRepository):
    """Legacy import path for the session repository."""


class AppFirestoreStore(AppFirestoreRepository):
    """Legacy facade that composes Firestore concrete repositories."""

    user_repository_cls = FirestoreUserStore
    wordpack_repository_cls = FirestoreWordPackStore
    example_repository_cls = FirestoreExampleStore
    article_repository_cls = FirestoreArticleStore
    quiz_repository_cls = FirestoreQuizStore
    regenerate_job_repository_cls = FirestoreRegenerateJobStore
    session_repository_cls = FirestoreSessionStore


__all__ = [
    "AppFirestoreStore",
    "FirestoreArticleStore",
    "FirestoreBaseStore",
    "FirestoreExampleStore",
    "FirestoreQuizStore",
    "FirestoreRegenerateJobStore",
    "FirestoreSessionStore",
    "FirestoreUserStore",
    "FirestoreWordPackStore",
    "firestore",
    "_build_search_payload",
    "_coerce_firestore_snapshot",
    "_extract_count_from_aggregation",
    "_extract_example_total",
    "_extract_search_terms",
    "_normalize_search_text",
    "_now_iso",
]
