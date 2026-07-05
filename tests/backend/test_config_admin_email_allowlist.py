import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

from backend.config import Settings  # noqa: E402  # isort:skip

_SAFE_SECRET = "b7K2m9Q4t1L6v3C8p5J0x2Z7n4Q1m6T9"  # 32文字の擬似乱数
_CLOUD_RUN_HOST = "app-1234567890-uc.a.run.app"

os.environ.setdefault("SESSION_SECRET_KEY", _SAFE_SECRET)


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """各テストで許可リストとシークレットを初期化し、副作用を遮断する。"""

    monkeypatch.setenv("SESSION_SECRET_KEY", _SAFE_SECRET)
    monkeypatch.delenv("ADMIN_EMAIL_ALLOWLIST", raising=False)


def test_production_requires_allowlist() -> None:
    """本番環境では ADMIN_EMAIL_ALLOWLIST が空だと起動に失敗する。"""

    with pytest.raises(ValueError):
        Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST,),
        disable_session_auth=False,
        _env_file=None,
    )


def test_production_accepts_non_empty_allowlist() -> None:
    """管理者メールアドレスを列挙すれば本番でも受理される。"""

    config = Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST,),
        admin_email_allowlist=("admin@example.com", "owner@example.com"),
        disable_session_auth=False,
        _env_file=None,
    )

    assert config.admin_email_allowlist == ("admin@example.com", "owner@example.com")


@pytest.mark.parametrize("environment", ["development", "staging"])
def test_non_production_can_skip_allowlist(environment: str) -> None:
    """非本番環境では従来どおり許可リストなしで起動できる。"""

    config = Settings(environment=environment, _env_file=None)

    assert config.admin_email_allowlist == ()


def test_allowlist_accepts_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """カンマ区切りで指定した環境変数を JSON と誤解釈せずに読み込める。"""

    monkeypatch.setenv("ADMIN_EMAIL_ALLOWLIST", "Admin@example.com,owner@example.com")

    config = Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST,),
        session_secret_key=_SAFE_SECRET,
        disable_session_auth=False,
        _env_file=None,
    )

    assert config.admin_email_allowlist == ("admin@example.com", "owner@example.com")
