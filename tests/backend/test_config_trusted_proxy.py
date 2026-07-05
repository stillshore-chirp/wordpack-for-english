"""Settings における Trusted Proxy 既定値の挙動を検証するテスト。"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.config import Settings  # noqa: E402  # isort:skip

_SAFE_SECRET = "r8YvT1nM4qL7s0P3w6B9c2F5h8J1k4L7"  # 32文字の擬似乱数
_CLOUD_RUN_HOST = "app-1234567890-uc.a.run.app"

os.environ.setdefault("SESSION_SECRET_KEY", _SAFE_SECRET)


@pytest.fixture(autouse=True)
def _reset_proxy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """各テストを独立させ、Trusted Proxy 関連の既定値を正しく検証する。"""

    monkeypatch.setenv("SESSION_SECRET_KEY", _SAFE_SECRET)
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)


def test_production_defaults_to_cloud_run_ranges() -> None:
    """ENVIRONMENT=production では Cloud Run/LB の CIDR が自動適用される。"""

    config = Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST,),
        admin_email_allowlist=("admin@example.com",),
        disable_session_auth=False,
        _env_file=None,
    )
    assert config.trusted_proxy_ips == ("35.191.0.0/16", "130.211.0.0/22")


def test_production_requires_explicit_proxy_when_overridden() -> None:
    """本番環境で空集合を指定すると安全のため起動に失敗する。"""

    with pytest.raises(ValueError):
        Settings(
            environment="production",
            trusted_proxy_ips=(),
            allowed_hosts=(_CLOUD_RUN_HOST,),
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=False,
            _env_file=None,
        )


def test_development_keeps_loopback_default() -> None:
    """開発環境では従来どおり 127.0.0.1 のみを信頼する。"""

    config = Settings(environment="development", _env_file=None)
    assert config.trusted_proxy_ips == ("127.0.0.1",)
