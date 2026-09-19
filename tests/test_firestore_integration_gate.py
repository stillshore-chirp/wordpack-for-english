from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_synthetic_pytest(
    tmp_path: Path,
    source: str,
    *,
    required: bool,
    selection: str | None = None,
    selection_flag: str = "-m",
    collect_only: bool = False,
) -> subprocess.CompletedProcess[str]:
    test_path = tmp_path / "test_synthetic_firestore_gate.py"
    test_path.write_text(source, encoding="utf-8")
    env = os.environ.copy()
    env["FIRESTORE_INTEGRATION_REQUIRED"] = "true" if required else "false"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--no-cov",
        "-c",
        str(REPO_ROOT / "pytest.ini"),
        "-p",
        "tests.conftest",
    ]
    if selection is not None:
        command.extend([selection_flag, selection])
    if collect_only:
        command.append("--collect-only")
    command.append(str(test_path))
    return subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_required_gate_fails_when_marker_selection_collects_no_target(tmp_path: Path) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_required_target():
    assert True

def test_unrelated_success():
    assert True
""",
        required=True,
        selection="not firestore_integration",
    )

    assert result.returncode != 0
    assert "no firestore_integration target was collected" in result.stdout


def test_required_gate_fails_when_keyword_selection_collects_no_target(tmp_path: Path) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_required_target():
    assert True

def test_unrelated_success():
    assert True
""",
        required=True,
        selection="unrelated_name",
        selection_flag="-k",
    )

    assert result.returncode != 0
    assert "no firestore_integration target was collected" in result.stdout


def test_required_gate_fails_when_every_target_is_skipped(tmp_path: Path) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_skipped_target():
    pytest.skip("synthetic unavailable emulator")

def test_unrelated_success():
    assert True
""",
        required=True,
    )

    assert result.returncode != 0
    assert "all firestore_integration targets were skipped" in result.stdout


def test_required_gate_succeeds_when_target_passes_and_unrelated_test_skips(
    tmp_path: Path,
) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_required_target():
    assert True

def test_unrelated_skip():
    pytest.skip("unrelated optional case")
""",
        required=True,
    )

    assert result.returncode == 0


def test_required_gate_fails_during_collect_only(tmp_path: Path) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_required_target():
    assert True

def test_unrelated_success():
    assert True
""",
        required=True,
        collect_only=True,
    )

    assert result.returncode != 0
    assert "all firestore_integration targets were skipped" in result.stdout


def test_optional_gate_allows_explicit_local_skip(tmp_path: Path) -> None:
    result = _run_synthetic_pytest(
        tmp_path,
        """
import pytest

@pytest.mark.firestore_integration
def test_optional_target():
    pytest.skip("synthetic unavailable emulator")
""",
        required=False,
    )

    assert result.returncode == 0
