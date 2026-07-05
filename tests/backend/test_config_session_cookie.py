"""Settings におけるセッション Cookie Secure 既定値の挙動を検証するテスト。"""

import os
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

_SAFE_SECRET = "Z8nQ1rV4tY7wB0cD3fG6hJ9kL2mP5sX1"  # 32文字の擬似乱数
_CLOUD_RUN_HOST = "app-1234567890-uc.a.run.app"

os.environ.setdefault("SESSION_SECRET_KEY", _SAFE_SECRET)

from backend.config import Settings


@pytest.fixture(autouse=True)
def clear_session_cookie_secure_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """環境変数の影響を排除し、純粋な既定値を検証する。"""

    monkeypatch.delenv("SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SESSION_SECRET_KEY", _SAFE_SECRET)


def test_session_cookie_secure_defaults_to_false_in_development() -> None:
    """開発環境では Secure を無効化したまま Cookie を配信できる。"""

    config = Settings(environment="development", _env_file=None)
    assert config.session_cookie_secure is False


def test_session_cookie_secure_defaults_to_true_in_production() -> None:
    """本番環境では Secure 属性が既定で有効化される。"""

    config = Settings(
        environment="production",
        allowed_hosts=(_CLOUD_RUN_HOST,),
        admin_email_allowlist=("admin@example.com",),
        disable_session_auth=False,
        _env_file=None,
    )
    assert config.session_cookie_secure is True


def test_session_cookie_secure_respects_explicit_override() -> None:
    """環境変数やコードで明示した値は本番でも優先される。"""

    config = Settings(
        environment="production",
        session_cookie_secure=False,
        allowed_hosts=(_CLOUD_RUN_HOST,),
        admin_email_allowlist=("admin@example.com",),
        disable_session_auth=False,
        _env_file=None,
    )
    assert config.session_cookie_secure is False


def test_production_rejects_disabled_session_auth() -> None:
    """本番環境ではセッション認証無効化を拒否する。"""

    with pytest.raises(ValueError, match="DISABLE_SESSION_AUTH"):
        Settings(
            environment="production",
            allowed_hosts=(_CLOUD_RUN_HOST,),
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=True,
            _env_file=None,
        )


def test_production_rejects_disabled_csrf_protection() -> None:
    """本番環境では CSRF ガード無効化を拒否する。"""

    with pytest.raises(ValueError, match="CSRF_PROTECTION_ENABLED"):
        Settings(
            environment="production",
            allowed_hosts=(_CLOUD_RUN_HOST,),
            admin_email_allowlist=("admin@example.com",),
            disable_session_auth=False,
            csrf_protection_enabled=False,
            _env_file=None,
        )
