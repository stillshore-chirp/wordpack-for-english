import os

from fastapi import APIRouter
from ..config import settings


router = APIRouter()


@router.get("/config")
def get_runtime_config() -> dict[str, object]:
    """Expose runtime config needed by the frontend.

    フロントエンドが同期すべき実行時設定を返す。現状は
    フロントのリクエスト・タイムアウト(ms)をサーバの env に
    揃えるために `llm_timeout_ms` をそのまま返す。
    """
    payload: dict[str, object] = {
        "request_timeout_ms": settings.llm_timeout_ms,
        "llm_model": settings.llm_model,
        "session_auth_disabled": settings.disable_session_auth,
        "google_client_id": settings.google_client_id,
    }
    if deployment_version := os.getenv("DEPLOYMENT_VERSION", "").strip():
        payload["deployment_version"] = deployment_version
    return payload
