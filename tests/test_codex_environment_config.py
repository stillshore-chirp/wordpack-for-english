from __future__ import annotations

import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT_PATH = REPO_ROOT / ".codex/environments/environment.toml"
# These substring sets are a bounded contract for the current direct configuration.
KNOWN_LONG_LIVED_START_COMMANDS = (
    "docker compose up",
    "docker-compose up",
    "uvicorn",
    "npm run dev",
    "start_firestore_emulator",
)
BROAD_CLEANUP_COMMANDS = (
    "docker compose down",
    "docker-compose down",
    "--remove-orphans",
    "pkill",
    "killall",
    "rm -rf",
)


def _load_environment() -> dict[str, object]:
    return tomllib.loads(ENVIRONMENT_PATH.read_text(encoding="utf-8"))


def test_cleanup_is_generic_intentional_noop_without_platform_override() -> None:
    config = _load_environment()
    cleanup = config["cleanup"]

    assert cleanup == {"script": ""}
    assert "darwin" not in cleanup


def test_configured_setup_scripts_do_not_include_known_long_lived_starts_or_broad_cleanup() -> None:
    config = _load_environment()

    setup_config = config["setup"]
    for setup in (setup_config, setup_config["darwin"]):
        script = setup["script"].lower()

        assert not any(command in script for command in KNOWN_LONG_LIVED_START_COMMANDS)
        assert not any(command in script for command in BROAD_CLEANUP_COMMANDS)
