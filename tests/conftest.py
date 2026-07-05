"""Pytest configuration to ensure session-less backend access during tests."""

import os

# Disable session authentication by default so API tests can call endpoints without
# provisioning cookies. Individual tests can override this via monkeypatch when needed.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DISABLE_SESSION_AUTH", "true")
# Provide a deterministic yet secure-length session secret for tests to satisfy
# 起動時バリデーション。実運用では `.env` で個別に乱数値を設定すること。
os.environ.setdefault("SESSION_SECRET_KEY", "S9kD2fH5jL8pQ1tV4yX7zB0cN3mR6wA9")
# Keep backend tests deterministic even when a developer's local .env contains
# real provider credentials.
os.environ.setdefault("LLM_PROVIDER", "local")
os.environ.setdefault("EMBEDDING_PROVIDER", "local")
