#!/usr/bin/env python3
"""Download one same-run Actions artifact and publish it after strict validation."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import select
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zipfile


CHUNK_SIZE = 64 * 1024
METADATA_LIMIT = 64 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 15 * 60
NO_PROGRESS_TIMEOUT_SECONDS = 60


class ArtifactDownloadError(Exception):
    """An expected, sanitized artifact-download failure."""


class ArtifactPolicy:
    def __init__(
        self,
        max_archive_bytes: int,
        max_uncompressed_bytes: int,
        max_file_bytes: int,
        max_entries: int,
        max_central_directory_bytes: int,
        exact_files: frozenset[str] | None = None,
    ) -> None:
        self.max_archive_bytes = max_archive_bytes
        self.max_uncompressed_bytes = max_uncompressed_bytes
        self.max_file_bytes = max_file_bytes
        self.max_entries = max_entries
        self.max_central_directory_bytes = max_central_directory_bytes
        self.exact_files = exact_files


ARTIFACT_POLICIES = {
    "frontend-release-dist": ArtifactPolicy(
        max_archive_bytes=1024 * 1024 * 1024,
        max_uncompressed_bytes=2 * 1024 * 1024 * 1024,
        max_file_bytes=512 * 1024 * 1024,
        max_entries=20_000,
        max_central_directory_bytes=16 * 1024 * 1024,
    ),
    "backend-image-archive": ArtifactPolicy(
        max_archive_bytes=4 * 1024 * 1024 * 1024,
        max_uncompressed_bytes=4 * 1024 * 1024 * 1024,
        max_file_bytes=4 * 1024 * 1024 * 1024,
        max_entries=8,
        max_central_directory_bytes=1024 * 1024,
        exact_files=frozenset({"backend-image.tar.zst"}),
    ),
    "backend-attestation-metadata": ArtifactPolicy(
        max_archive_bytes=128 * 1024 * 1024,
        max_uncompressed_bytes=256 * 1024 * 1024,
        max_file_bytes=128 * 1024 * 1024,
        max_entries=32,
        max_central_directory_bytes=1024 * 1024,
        exact_files=frozenset(
            {"backend-provenance.json", "backend-image.sbom.spdx.json"}
        ),
    ),
}


def _normalize_digest(value: object, *, api_value: bool = False) -> str:
    if not isinstance(value, str):
        raise ArtifactDownloadError("artifact digest is missing or invalid")
    if api_value:
        if not value.startswith("sha256:"):
            raise ArtifactDownloadError("artifact digest is missing or invalid")
        value = value.removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ArtifactDownloadError("artifact digest is missing or invalid")
    return value


def _expected_destination(name: str, workspace: Path, runner_temp: Path) -> Path:
    if name == "frontend-release-dist":
        return workspace / "apps" / "frontend" / "dist"
    if name == "backend-image-archive":
        return runner_temp / "backend-image"
    if name == "backend-attestation-metadata":
        return workspace / ".backend-attestation"
    raise ArtifactDownloadError("artifact name is not allowed")


def _validate_destination(destination: Path) -> None:
    destination = Path(os.path.abspath(destination))
    for parent in reversed(destination.parents):
        try:
            mode = parent.lstat().st_mode
        except FileNotFoundError:
            raise ArtifactDownloadError("artifact destination parent is missing") from None
        if not stat.S_ISDIR(mode) or stat.S_ISLNK(mode):
            raise ArtifactDownloadError("artifact destination parent is unsafe")
    try:
        info = destination.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode):
        raise ArtifactDownloadError("artifact destination is a symbolic link")
    if not stat.S_ISDIR(info.st_mode):
        raise ArtifactDownloadError("artifact destination is not a directory")
    try:
        next(destination.iterdir())
    except StopIteration:
        return
    raise ArtifactDownloadError("artifact destination is not empty")


def _validate_metadata(
    metadata: object,
    *,
    artifact_id: int,
    name: str,
    run_id: int,
    upload_digest: str,
    policy: ArtifactPolicy,
) -> int:
    if not isinstance(metadata, dict):
        raise ArtifactDownloadError("artifact metadata is invalid")
    run = metadata.get("workflow_run")
    size = metadata.get("size_in_bytes")
    if (
        metadata.get("id") != artifact_id
        or metadata.get("name") != name
        or metadata.get("expired") is not False
        or not isinstance(run, dict)
        or run.get("id") != run_id
        or not isinstance(size, int)
        or isinstance(size, bool)
        or size <= 0
        or size > policy.max_archive_bytes
    ):
        raise ArtifactDownloadError("artifact metadata does not match this run")
    if _normalize_digest(metadata.get("digest"), api_value=True) != upload_digest:
        raise ArtifactDownloadError("artifact metadata digest does not match upload")
    return size


def _api_endpoint(repo: str, artifact_id: int, *, archive: bool = False) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ArtifactDownloadError("repository identifier is invalid")
    owner, repository = repo.split("/", 1)
    if owner in {".", ".."} or repository in {".", ".."}:
        raise ArtifactDownloadError("repository identifier is invalid")
    suffix = "/zip" if archive else ""
    return f"repos/{repo}/actions/artifacts/{artifact_id}{suffix}"


def _stream_gh_api(endpoint: str, sink, max_bytes: int) -> tuple[int, str]:
    command = ["gh", "api", "--hostname", "github.com", endpoint]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise ArtifactDownloadError("GitHub artifact API request could not start") from None

    if process.stdout is None:
        process.kill()
        process.wait()
        raise ArtifactDownloadError("GitHub artifact API response is unavailable")

    digest = hashlib.sha256()
    received = 0
    started = last_progress = time.monotonic()
    try:
        while True:
            now = time.monotonic()
            if (
                now - started > DOWNLOAD_TIMEOUT_SECONDS
                or now - last_progress > NO_PROGRESS_TIMEOUT_SECONDS
            ):
                raise ArtifactDownloadError("GitHub artifact API request timed out")
            ready, _, _ = select.select([process.stdout], [], [], 0.5)
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), CHUNK_SIZE)
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                raise ArtifactDownloadError("GitHub artifact API response exceeds its limit")
            sink.write(chunk)
            digest.update(chunk)
            last_progress = time.monotonic()
        return_code = process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        raise ArtifactDownloadError("GitHub artifact API request failed") from None
    except ArtifactDownloadError:
        raise
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()
    if return_code != 0:
        raise ArtifactDownloadError("GitHub artifact API request failed")
    return received, digest.hexdigest()


def _safe_member_path(info: zipfile.ZipInfo) -> tuple[str, bool]:
    raw_name = getattr(info, "orig_filename", info.filename)
    if (
        not isinstance(raw_name, str)
        or not raw_name
        or "\x00" in raw_name
        or "\\" in raw_name
        or raw_name.startswith("/")
        or re.match(r"^[A-Za-z]:", raw_name)
    ):
        raise ArtifactDownloadError("artifact archive contains an unsafe path")
    is_directory = info.is_dir()
    name = raw_name[:-1] if is_directory and raw_name.endswith("/") else raw_name
    parts = name.split("/")
    if (
        not name
        or any(part in ("", ".", "..") for part in parts)
        or ":" in name
    ):
        raise ArtifactDownloadError("artifact archive contains an unsafe path")
    normalized = "/".join(parts)
    if not normalized:
        raise ArtifactDownloadError("artifact archive contains an unsafe path")

    unix_mode = (info.external_attr >> 16) & 0xFFFF
    file_type = stat.S_IFMT(unix_mode)
    allowed_types = {0, stat.S_IFDIR} if is_directory else {0, stat.S_IFREG}
    if file_type not in allowed_types or info.flag_bits & 0x1:
        raise ArtifactDownloadError("artifact archive contains a special file")
    if is_directory and info.file_size != 0:
        raise ArtifactDownloadError("artifact directory entry contains data")
    return normalized, is_directory


def _validate_zip_directory(archive_path: Path, policy: ArtifactPolicy) -> None:
    """Bound central-directory allocation before zipfile materializes entries."""
    try:
        file_size = archive_path.stat().st_size
        with archive_path.open("rb") as source:
            tail_size = min(file_size, 22 + 65_535)
            source.seek(file_size - tail_size)
            tail = source.read(tail_size)
    except OSError:
        raise ArtifactDownloadError("artifact archive is unavailable") from None

    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or len(tail) - offset < 22:
        raise ArtifactDownloadError("artifact ZIP directory is invalid")
    try:
        (
            _signature,
            disk_number,
            directory_disk,
            disk_entries,
            total_entries,
            directory_size,
            directory_offset,
            comment_size,
        ) = struct.unpack_from("<4s4H2LH", tail, offset)
    except struct.error:
        raise ArtifactDownloadError("artifact ZIP directory is invalid") from None
    eocd_offset = file_size - tail_size + offset
    if (
        offset + 22 + comment_size != len(tail)
        or disk_number != 0
        or directory_disk != 0
        or disk_entries != total_entries
        or total_entries in (0, 0xFFFF)
        or total_entries > policy.max_entries
        or directory_size == 0xFFFFFFFF
        or directory_offset == 0xFFFFFFFF
        or directory_size > policy.max_central_directory_bytes
        or directory_offset + directory_size != eocd_offset
    ):
        raise ArtifactDownloadError("artifact ZIP directory exceeds its limits")


def _validate_entries(
    infos: list[zipfile.ZipInfo], policy: ArtifactPolicy
) -> tuple[list[tuple[zipfile.ZipInfo, str, bool]], int]:
    if not infos or len(infos) > policy.max_entries:
        raise ArtifactDownloadError("artifact archive entry count is invalid")
    records: list[tuple[zipfile.ZipInfo, str, bool]] = []
    seen: dict[str, bool] = {}
    regular_files: set[str] = set()
    total_size = 0
    for info in infos:
        name, is_directory = _safe_member_path(info)
        if name in seen:
            raise ArtifactDownloadError("artifact archive contains duplicate paths")
        parts = name.split("/")
        for index in range(1, len(parts)):
            parent = "/".join(parts[:index])
            if seen.get(parent) is False:
                raise ArtifactDownloadError("artifact archive has a file path conflict")
        if not is_directory and any(existing.startswith(name + "/") for existing in seen):
            raise ArtifactDownloadError("artifact archive has a file path conflict")
        if not is_directory:
            if info.file_size < 0 or info.file_size > policy.max_file_bytes:
                raise ArtifactDownloadError("artifact file exceeds its limit")
            total_size += info.file_size
            regular_files.add(name)
        seen[name] = is_directory
        records.append((info, name, is_directory))
    if total_size > policy.max_uncompressed_bytes:
        raise ArtifactDownloadError("artifact archive exceeds its uncompressed limit")
    if policy.exact_files is not None and regular_files != set(policy.exact_files):
        raise ArtifactDownloadError("artifact archive contents do not match its type")
    if not regular_files:
        raise ArtifactDownloadError("artifact archive contains no files")
    return records, total_size


def _extract_zip(archive_path: Path, destination: Path, policy: ArtifactPolicy) -> None:
    _validate_destination(destination)
    _validate_zip_directory(archive_path, policy)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            records, expected_total = _validate_entries(archive.infolist(), policy)
            actual_total = 0
            for info, name, is_directory in records:
                target = destination.joinpath(*name.split("/"))
                if is_directory:
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with archive.open(info, "r") as source, target.open("xb") as output:
                    while chunk := source.read(CHUNK_SIZE):
                        written += len(chunk)
                        actual_total += len(chunk)
                        if (
                            written > policy.max_file_bytes
                            or actual_total > policy.max_uncompressed_bytes
                        ):
                            raise ArtifactDownloadError("artifact content exceeds its limit")
                        output.write(chunk)
                if written != info.file_size:
                    raise ArtifactDownloadError("artifact file size does not match its index")
            if actual_total != expected_total:
                raise ArtifactDownloadError("artifact size does not match its index")
    except ArtifactDownloadError:
        raise
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, zipfile.LargeZipFile):
        raise ArtifactDownloadError("artifact archive is invalid") from None


def download_artifact(
    *,
    artifact_id: int,
    name: str,
    upload_digest: str,
    destination: Path,
    repo: str,
    run_id: int,
    runner_temp: Path,
    workspace: Path,
) -> None:
    policy = ARTIFACT_POLICIES.get(name)
    if policy is None:
        raise ArtifactDownloadError("artifact name is not allowed")
    if artifact_id <= 0 or run_id <= 0:
        raise ArtifactDownloadError("artifact identifier is invalid")
    if _normalize_digest(upload_digest) != upload_digest:
        raise ArtifactDownloadError("upload digest is invalid")
    expected_destination = _expected_destination(name, workspace, runner_temp)
    if Path(os.path.abspath(destination)) != Path(os.path.abspath(expected_destination)):
        raise ArtifactDownloadError("artifact destination is not allowed")
    _validate_destination(expected_destination)
    if not runner_temp.is_dir() or runner_temp.is_symlink():
        raise ArtifactDownloadError("temporary directory is unsafe")

    metadata_sink = io.BytesIO()
    _stream_gh_api(
        _api_endpoint(repo, artifact_id), metadata_sink, METADATA_LIMIT
    )
    try:
        metadata = json.loads(metadata_sink.getvalue())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ArtifactDownloadError("artifact metadata is invalid") from None
    archive_size = _validate_metadata(
        metadata,
        artifact_id=artifact_id,
        name=name,
        run_id=run_id,
        upload_digest=upload_digest,
        policy=policy,
    )

    with tempfile.TemporaryDirectory(prefix="ci-artifact-", dir=runner_temp) as temporary:
        temporary_root = Path(temporary)
        archive_path = temporary_root / "artifact.zip"
        with archive_path.open("xb") as archive_file:
            received, actual_digest = _stream_gh_api(
                _api_endpoint(repo, artifact_id, archive=True),
                archive_file,
                min(archive_size, policy.max_archive_bytes),
            )
        if received != archive_size or actual_digest != upload_digest:
            raise ArtifactDownloadError("downloaded artifact digest does not match upload")

        with tempfile.TemporaryDirectory(
            prefix=".ci-artifact-stage-", dir=expected_destination.parent
        ) as stage:
            staged_payload = Path(stage) / "payload"
            staged_payload.mkdir(mode=0o700)
            _extract_zip(archive_path, staged_payload, policy)
            _validate_destination(expected_destination)
            try:
                os.replace(staged_payload, expected_destination)
            except OSError:
                raise ArtifactDownloadError("artifact could not be published safely") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True, type=int)
    parser.add_argument("--name", required=True, choices=sorted(ARTIFACT_POLICIES))
    parser.add_argument("--digest", required=True)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    workspace = os.environ.get("GITHUB_WORKSPACE", "")
    runner_temp = os.environ.get("RUNNER_TEMP", "")
    if not token or not repo or not run_id.isdigit() or not workspace or not runner_temp:
        parser.error("required GitHub Actions context is unavailable")
    try:
        download_artifact(
            artifact_id=args.artifact_id,
            name=args.name,
            upload_digest=args.digest,
            destination=args.destination,
            repo=repo,
            run_id=int(run_id),
            runner_temp=Path(runner_temp),
            workspace=Path(workspace),
        )
    except ArtifactDownloadError as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1
    except Exception:
        print("::error::artifact download failed safely", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
