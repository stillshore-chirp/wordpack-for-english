from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

WordPackTuple = tuple[str, str, str, str]
WordPackListTuple = tuple[str, str, str, str, str]
WordPackListFlagsTuple = tuple[
    str,
    str,
    str,
    str,
    str,
    bool,
    Mapping[str, int],
    int,
    int,
    bool,
]


class WordPackRepository(Protocol):
    def get_word_pack(self, word_pack_id: str) -> WordPackTuple | None:
        ...

    def save_word_pack(
        self,
        word_pack_id: str,
        lemma: str,
        data_json: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        ...

    def delete_word_pack(self, word_pack_id: str) -> bool:
        ...

    def find_word_pack_id_by_lemma(self, lemma: str) -> str | None:
        ...

    def find_word_pack_by_lemma_ci(self, lemma: str) -> tuple[str, str, str] | None:
        ...

    def list_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[WordPackListFlagsTuple]:
        ...

    def list_public_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[WordPackListFlagsTuple]:
        ...

    def list_all_word_packs_with_flags(self) -> list[WordPackListFlagsTuple]:
        ...

    def list_all_public_word_packs_with_flags(
        self,
    ) -> list[WordPackListFlagsTuple]:
        ...

    def list_owned_word_packs_with_flags(
        self, owner_user_id: str, limit: int = 50, offset: int = 0
    ) -> list[WordPackListFlagsTuple]:
        ...

    def list_all_owned_word_packs_with_flags(
        self, owner_user_id: str
    ) -> list[WordPackListFlagsTuple]:
        ...

    def count_word_packs(self) -> int:
        ...

    def count_public_word_packs(self) -> int:
        ...

    def count_owned_word_packs(self, owner_user_id: str) -> int:
        ...

    def is_word_pack_guest_public(self, word_pack_id: str) -> bool:
        ...

    def update_word_pack_study_progress(
        self, word_pack_id: str, checked_increment: int, learned_increment: int
    ) -> tuple[int, int] | None:
        ...
