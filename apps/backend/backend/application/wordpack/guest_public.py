from __future__ import annotations

from dataclasses import dataclass

from ..common.errors import NotFoundError


@dataclass(frozen=True)
class UpdateWordPackGuestPublicCommand:
    word_pack_id: str
    guest_public: bool
    updated_at: str


@dataclass(frozen=True)
class UpdateWordPackGuestPublicResult:
    word_pack_id: str
    guest_public: bool


def update_guest_public_flag(
    *,
    repository: object,
    command: UpdateWordPackGuestPublicCommand,
) -> UpdateWordPackGuestPublicResult:
    metadata = repository.get_word_pack_metadata(command.word_pack_id)
    if metadata is None:
        raise NotFoundError("WordPack not found")

    repository.update_word_pack_metadata(
        command.word_pack_id,
        updated_at=command.updated_at,
        guest_public=command.guest_public,
    )

    return UpdateWordPackGuestPublicResult(
        word_pack_id=command.word_pack_id,
        guest_public=command.guest_public,
    )
