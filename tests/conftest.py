"""Pytest configuration and required integration-gate enforcement."""

from dataclasses import dataclass, field
import os

import pytest

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


FIRESTORE_INTEGRATION_MARK = "firestore_integration"
FIRESTORE_INTEGRATION_REQUIRED_ENV = "FIRESTORE_INTEGRATION_REQUIRED"


def _firestore_integration_required() -> bool:
    """Return whether the current pytest process owns the required gate."""

    return os.environ.get(FIRESTORE_INTEGRATION_REQUIRED_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


@dataclass
class _FirestoreGateState:
    required: bool
    target_nodeids: set[str] = field(default_factory=set)
    passed: int = 0
    skipped: int = 0


_firestore_gate_state: _FirestoreGateState | None = None


def pytest_configure(config: pytest.Config) -> None:
    """Capture the explicit CI-only requirement for the Firestore gate."""

    global _firestore_gate_state
    _firestore_gate_state = _FirestoreGateState(_firestore_integration_required())


def pytest_collection_finish(session: pytest.Session) -> None:
    """Remember the required target set after collection and selection filters."""

    if _firestore_gate_state is None or not _firestore_gate_state.required:
        return
    _firestore_gate_state.target_nodeids = {
        item.nodeid
        for item in session.items
        if item.get_closest_marker(FIRESTORE_INTEGRATION_MARK) is not None
    }


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Count successful and skipped required targets without changing optional runs."""

    if (
        _firestore_gate_state is None
        or not _firestore_gate_state.required
        or report.nodeid not in _firestore_gate_state.target_nodeids
    ):
        return
    if report.when == "call" and report.passed:
        _firestore_gate_state.passed += 1
    elif report.skipped and report.when in {"setup", "call"}:
        _firestore_gate_state.skipped += 1


def pytest_sessionfinish(
    session: pytest.Session, exitstatus: pytest.ExitCode
) -> None:
    """Fail required CI when the marked integration target is absent or skipped."""

    del exitstatus
    state = _firestore_gate_state
    if state is None or not state.required:
        return

    if state.target_nodeids and state.passed > 0:
        return

    if not state.target_nodeids:
        reason = "no firestore_integration target was collected"
    else:
        reason = (
            "all firestore_integration targets were skipped or did not complete "
            f"successfully (targets={len(state.target_nodeids)}, skipped={state.skipped})"
        )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
    terminal = session.config.pluginmanager.get_plugin("terminalreporter")
    if terminal is not None:
        terminal.write_line(
            "Firestore integration gate is required but incomplete: " + reason,
            red=True,
        )
