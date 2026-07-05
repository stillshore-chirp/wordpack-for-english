from __future__ import annotations

from importlib import import_module
from collections.abc import Mapping
from typing import Any, Awaitable, Callable

from fastapi import Request

from ...infrastructure.llm.wordpack_generator import run_wordpack_flow as _run_wordpack_flow
from ...auth import get_current_user
from ...config import settings
from ...id_factory import generate_word_pack_id as _generate_word_pack_id
from ...store import store as _default_store
from ...store.proxy import CurrentStoreProxy

store = CurrentStoreProxy(_default_store)
generate_word_pack_id = _generate_word_pack_id
run_wordpack_flow = _run_wordpack_flow


async def require_authenticated_user(request: Request) -> dict[str, str]:
    """ゲストを拒否するための認証依存関数（テスト時は無効化設定に合わせる）。"""

    # なぜ: DISABLE_SESSION_AUTH が有効な検証環境でも生成系 API を動かせるようにしつつ、
    #       本番では get_current_user でゲスト拒否とセッション検証を強制する。
    if settings.disable_session_auth:
        return {"mode": "test"}
    return await get_current_user(request)


def _word_router_package() -> Any | None:
    try:
        return import_module("backend.routers.word")
    except Exception:
        return None


def get_store() -> Any:
    package = _word_router_package()
    return getattr(package, "store", store)


def next_word_pack_id() -> str:
    package = _word_router_package()
    generator = getattr(package, "generate_word_pack_id", generate_word_pack_id)
    return str(generator())


def get_run_wordpack_flow() -> Callable[..., Awaitable[Any]]:
    package = _word_router_package()
    return getattr(package, "run_wordpack_flow", run_wordpack_flow)


def get_word_pack_visibility(repository: Any, word_pack_id: str) -> Mapping[str, Any] | None:
    resolver = getattr(repository, "get_word_pack_visibility", None)
    if callable(resolver):
        return resolver(word_pack_id)

    get_word_pack = getattr(repository, "get_word_pack", None)
    if callable(get_word_pack) and get_word_pack(word_pack_id) is None:
        return None

    guest_public = False
    is_guest_public = getattr(repository, "is_word_pack_guest_public", None)
    if callable(is_guest_public):
        guest_public = bool(is_guest_public(word_pack_id))

    owner_user_id = None
    get_metadata = getattr(repository, "get_word_pack_metadata", None)
    metadata_payload = get_metadata(word_pack_id) if callable(get_metadata) else None
    metadata = (
        metadata_payload.get("metadata")
        if isinstance(metadata_payload, Mapping)
        else None
    )
    if isinstance(metadata, Mapping):
        owner_raw = metadata.get("owner_user_id")
        owner_user_id = str(owner_raw).strip() if owner_raw else None

    return {"guest_public": guest_public, "owner_user_id": owner_user_id}
