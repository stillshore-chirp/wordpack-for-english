import os

from fastapi import APIRouter
from ..config import settings


router = APIRouter()


@router.get("/config")
def get_runtime_config() -> dict[str, object]:
    """Expose runtime config needed by the frontend.

    フロントエンドが同期すべき実行時設定を返す。通常APIと
    長時間生成フローを分離し、非生成UIが長時間停止しないようにする。
    """
    payload: dict[str, object] = {
        "request_timeout_ms": settings.request_timeout_ms,
        "generation_request_timeout_ms": settings.llm_request_timeout_ms,
        "llm_model": settings.llm_model,
        "session_auth_disabled": settings.disable_session_auth,
        "google_client_id": settings.google_client_id,
    }
    if deployment_version := os.getenv("DEPLOYMENT_VERSION", "").strip():
        payload["deployment_version"] = deployment_version
    return payload
