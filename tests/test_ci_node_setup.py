from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ACTION_DIR = ROOT / ".github/actions/setup-ci-node"
ACTION_FILE = ACTION_DIR / "action.yml"
SETUP_SCRIPT = ACTION_DIR / "setup.sh"
EXPECTED_VERSION = "v22.23.4"
EXPECTED_URL = "https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-x64.tar.xz"
EXPECTED_SHA256 = "1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce"


def _write_executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _runner_env(
    tmp_path: Path, *, uname: tuple[str, str] = ("Linux", "x86_64")
) -> tuple[dict[str, str], Path, Path, Path]:
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir()
    temp_dir = tmp_path / "runner-temp"
    temp_dir.mkdir()
    github_path = tmp_path / "github-path"
    curl_log = tmp_path / "curl-args"
    tar_log = tmp_path / "tar-called"
    _write_executable(
        bin_dir / "uname",
        "#!/bin/sh\n"
        f"if [ \"$1\" = -s ]; then printf '%s\\n' '{uname[0]}'; "
        f"else printf '%s\\n' '{uname[1]}'; fi\n",
    )
    _write_executable(
        bin_dir / "curl",
        "#!/bin/sh\n"
        "set -eu\n"
        "printf '%s\\n' \"$*\" > \"$TEST_CURL_LOG\"\n"
        "output=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = --output ]; then shift; output=$1; fi\n"
        "  shift\n"
        "done\n"
        "printf '%s' 'untrusted fixture bytes' > \"$output\"\n",
    )
    hash_script = (
        f"#!{sys.executable}\n"
        "import hashlib, os, pathlib, sys\n"
        "expected, file_name = sys.stdin.read().strip().split('  ', 1)\n"
        f"if os.environ.get('TEST_ACCEPT_PINNED_FIXTURE') == '1': raise SystemExit(0 if expected == '{EXPECTED_SHA256}' else 1)\n"
        "actual = hashlib.sha256(pathlib.Path(file_name).read_bytes()).hexdigest()\n"
        "raise SystemExit(0 if actual == expected else 1)\n"
    )
    _write_executable(bin_dir / "sha256sum", hash_script)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "RUNNER_TEMP": str(temp_dir),
        "GITHUB_PATH": str(github_path),
        "TEST_CURL_LOG": str(curl_log),
        "TEST_TAR_LOG": str(tar_log),
    }
    env.pop("RUNNER_TOOL_CACHE", None)
    return env, github_path, curl_log, tar_log


def _run_setup(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SETUP_SCRIPT)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )


def test_action_is_dependency_free_composite_without_override_inputs() -> None:
    action = yaml.safe_load(ACTION_FILE.read_text(encoding="utf-8"))

    assert action["runs"]["using"] == "composite"
    assert "inputs" not in action
    step = action["runs"]["steps"][0]
    assert step["env"] == {"ACTION_PATH": "${{ github.action_path }}"}
    assert step["run"] == 'bash "$ACTION_PATH/setup.sh"'


def test_correct_tool_cache_version_skips_download(tmp_path: Path) -> None:
    env, github_path, curl_log, _ = _runner_env(tmp_path)
    tool_cache = tmp_path / "tool-cache"
    cached_bin = tool_cache / "node/22.23.4/x64/bin"
    cached_bin.mkdir(parents=True)
    _write_executable(cached_bin / "node", f"#!/bin/sh\nprintf '%s\\n' '{EXPECTED_VERSION}'\n")
    env["RUNNER_TOOL_CACHE"] = str(tool_cache)

    result = _run_setup(env)

    assert result.returncode == 0, result.stderr
    assert github_path.read_text(encoding="utf-8") == f"{cached_bin}\n"
    assert not curl_log.exists()


def test_checksum_mismatch_stops_before_extraction_and_uses_fixed_https_url(
    tmp_path: Path,
) -> None:
    env, github_path, curl_log, tar_log = _runner_env(tmp_path)
    _write_executable(
        Path(env["PATH"].split(":", maxsplit=1)[0]) / "tar",
        "#!/bin/sh\nprintf called > \"$TEST_TAR_LOG\"\n",
    )

    result = _run_setup(env)

    assert result.returncode != 0
    assert "failed SHA-256 verification" in result.stderr
    assert not tar_log.exists()
    assert not github_path.exists()
    curl_args = curl_log.read_text(encoding="utf-8")
    assert EXPECTED_URL in curl_args
    assert "--proto =https" in curl_args
    assert "--proto-redir =https" in curl_args
    assert "--tlsv1.2" in curl_args
    assert "--max-time 120" in curl_args
    assert "--retry 3" in curl_args


def test_verified_fallback_installs_under_runner_temp(tmp_path: Path) -> None:
    env, github_path, curl_log, tar_log = _runner_env(tmp_path)
    env["TEST_ACCEPT_PINNED_FIXTURE"] = "1"
    _write_executable(
        Path(env["PATH"].split(":", maxsplit=1)[0]) / "tar",
        "#!/bin/sh\n"
        "set -eu\n"
        "destination=''\n"
        "while [ \"$#\" -gt 0 ]; do\n"
        "  if [ \"$1\" = --directory ]; then shift; destination=$1; fi\n"
        "  shift\n"
        "done\n"
        "mkdir -p \"$destination/bin\"\n"
        "printf '%s\\n' '#!/bin/sh' \"printf '%s\\\\n' 'v22.23.4'\" > \"$destination/bin/node\"\n"
        "chmod +x \"$destination/bin/node\"\n"
        "printf extracted > \"$TEST_TAR_LOG\"\n",
    )

    result = _run_setup(env)

    assert result.returncode == 0, result.stderr
    installed_bin = Path(github_path.read_text(encoding="utf-8").strip())
    assert installed_bin.is_relative_to(Path(env["RUNNER_TEMP"]))
    assert (installed_bin / "node").is_file()
    assert tar_log.read_text(encoding="utf-8") == "extracted"
    assert curl_log.exists()


def test_download_version_and_checksum_are_fixed_in_source() -> None:
    script = SETUP_SCRIPT.read_text(encoding="utf-8")

    assert 'readonly NODE_VERSION="22.23.4"' in script
    assert f'readonly NODE_ARCHIVE_SHA256="{EXPECTED_SHA256}"' in script
    assert 'readonly NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE}"' in script
    assert "NODE_VERSION:-" not in script
    assert "NODE_URL:-" not in script


def test_backend_jobs_set_up_checksum_pinned_node_before_firebase_tools_install() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))

    for job_name in ("backend", "backend_compatibility"):
        steps = workflow["jobs"][job_name]["steps"]
        setup_indexes = [
            index
            for index, step in enumerate(steps)
            if step.get("uses") == "./.github/actions/setup-ci-node"
        ]
        npm_indexes = [
            index
            for index, step in enumerate(steps)
            if "npm install -g firebase-tools@15.22.0" in step.get("run", "")
        ]

        assert len(setup_indexes) == 1, job_name
        assert len(npm_indexes) == 1, job_name
        assert setup_indexes[0] < npm_indexes[0], job_name


def test_unsupported_platform_stops_before_download(tmp_path: Path) -> None:
    env, github_path, curl_log, _ = _runner_env(tmp_path, uname=("Linux", "aarch64"))

    result = _run_setup(env)

    assert result.returncode != 0
    assert "Unsupported runner platform" in result.stderr
    assert not curl_log.exists()
    assert not github_path.exists()
