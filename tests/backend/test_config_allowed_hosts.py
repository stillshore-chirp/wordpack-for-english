"""Settings における ALLOWED_HOSTS の安全ガードを検証するテスト。"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.config import Settings  # noqa: E402  # isort:skip

_SAFE_SECRET = "w5F8t1R6y3K0d9L2p7Q4m8S1x6V3z0N5"  # 32文字の擬似乱数
_CLOUD_RUN_HOST = "app-1234567890-uc.a.run.app"

os.environ.setdefault("SESSION_SECRET_KEY", _SAFE_SECRET)


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """各テストの前後で環境変数をクリーンに保つ。"""

    monkeypatch.setenv("SESSION_SECRET_KEY", _SAFE_SECRET)
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)


def test_production_rejects_wildcard_hosts() -> None:
    """本番環境でワイルドカードを含む設定は拒否される。"""

    with pytest.raises(ValueError):
        Settings(
            environment="production",
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=False,
            _env_file=None,
        )

    with pytest.raises(ValueError):
        Settings(
            environment="production",
            allowed_hosts=("*", _CLOUD_RUN_HOST),
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=False,
            _env_file=None,
        )


def test_production_rejects_empty_hosts() -> None:
    """空配列のままでも create_app 側でワイルドカードにフォールバックするので拒否。"""

    with pytest.raises(ValueError):
        Settings(
            environment="production",
            allowed_hosts=(),
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=False,
            _env_file=None,
        )


def test_production_allows_explicit_hosts() -> None:
    """Cloud Run 既定ホストやカスタムドメインを列挙すれば受理される。"""

    config = Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST, "api.example.com"),
        admin_email_allowlist=("admin@example.com",),
        disable_session_auth=False,
        _env_file=None,
    )

    assert tuple(config.allowed_hosts) == (_CLOUD_RUN_HOST, "api.example.com")


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_non_production_can_keep_wildcard_hosts(environment: str) -> None:
    """docker-compose などの非本番環境では従来どおり * を許可する。"""

    config = Settings(environment=environment, allowed_hosts=("*",), _env_file=None)

    assert tuple(config.allowed_hosts) == ("*",)
