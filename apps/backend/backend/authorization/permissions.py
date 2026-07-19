from __future__ import annotations

from enum import StrEnum


class Permission(StrEnum):
    WORDPACK_READ = "wordpack:read"
    WORDPACK_CREATE = "wordpack:create"
    WORDPACK_UPDATE = "wordpack:update"
    WORDPACK_DELETE = "wordpack:delete"
    WORDPACK_GENERATE = "wordpack:generate"
    EXAMPLE_READ = "example:read"
    EXAMPLE_CREATE = "example:create"
    EXAMPLE_UPDATE = "example:update"
    EXAMPLE_DELETE = "example:delete"
    ARTICLE_READ = "article:read"
    ARTICLE_CREATE = "article:create"
    ARTICLE_UPDATE = "article:update"
    ARTICLE_DELETE = "article:delete"
    QUIZ_READ = "quiz:read"
    QUIZ_CREATE = "quiz:create"
    QUIZ_UPDATE = "quiz:update"
    QUIZ_DELETE = "quiz:delete"
    QUIZ_ATTEMPT_WRITE = "quiz_attempt:write"
    TTS_CREATE = "tts:create"
