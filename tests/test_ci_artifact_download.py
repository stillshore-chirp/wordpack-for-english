from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import zipfile

import pytest

from scripts import download_ci_artifact as downloader


DIGEST = "a" * 64


def _policy(**overrides: object) -> downloader.ArtifactPolicy:
    fields = {
        "max_archive_bytes": 1024,
        "max_uncompressed_bytes": 1024,
        "max_file_bytes": 1024,
        "max_entries": 16,
        "max_central_directory_bytes": 4096,
        "exact_files": None,
    }
    fields.update(overrides)
    return downloader.ArtifactPolicy(**fields)  # type: ignore[arg-type]


def _zip_bytes(entries: list[tuple[zipfile.ZipInfo | str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return buffer.getvalue()


def _valid_metadata(
    *, artifact_id: int = 42, name: str = "backend-image-archive", run_id: int = 17
) -> dict[str, object]:
    return {
        "id": artifact_id,
        "name": name,
        "expired": False,
        "size_in_bytes": 100,
        "digest": f"sha256:{DIGEST}",
        "workflow_run": {"id": run_id},
    }


def test_digest_normalizes_upload_and_api_formats_and_rejects_noncanonical_values() -> None:
    assert downloader._normalize_digest(DIGEST) == DIGEST
    assert downloader._normalize_digest(f"sha256:{DIGEST}", api_value=True) == DIGEST
    for invalid in ("A" * 64, "a" * 63, "sha256:" + DIGEST, None):
        with pytest.raises(downloader.ArtifactDownloadError):
            downloader._normalize_digest(invalid)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", 43),
        ("name", "other-artifact"),
        ("expired", True),
        ("workflow_run", {"id": 18}),
        ("digest", "sha256:" + "b" * 64),
        ("size_in_bytes", 1025),
    ],
)
def test_metadata_must_match_exact_artifact_and_current_run(
    field: str, value: object
) -> None:
    metadata = _valid_metadata()
    metadata[field] = value
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._validate_metadata(
            metadata,
            artifact_id=42,
            name="backend-image-archive",
            run_id=17,
            upload_digest=DIGEST,
            policy=_policy(),
        )


def test_artifact_names_and_destinations_are_allowlisted(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner-temp"
    (workspace / "apps" / "frontend").mkdir(parents=True)
    runner_temp.mkdir()
    assert downloader._expected_destination(
        "frontend-release-dist", workspace, runner_temp
    ) == workspace / "apps" / "frontend" / "dist"
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._expected_destination("arbitrary-name", workspace, runner_temp)
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader.download_artifact(
            artifact_id=42,
            name="arbitrary-name",
            upload_digest=DIGEST,
            destination=workspace / "unrelated",
            repo="owner/repo",
            run_id=17,
            runner_temp=runner_temp,
            workspace=workspace,
        )


@pytest.mark.parametrize("repo", ["../repo", "owner/../repo", "owner/.", "owner//repo"])
def test_api_endpoint_rejects_unsafe_repository_paths(repo: str) -> None:
    with pytest.raises(downloader.ArtifactDownloadError, match="repository identifier"):
        downloader._api_endpoint(repo, 42)


def test_gh_api_transport_is_pinned_and_streams_with_a_hard_byte_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"synthetic response"
    captured: dict[str, object] = {}

    class FakeProcess:
        def __init__(self, output: bytes) -> None:
            read_fd, write_fd = os.pipe()
            os.write(write_fd, output)
            os.close(write_fd)
            self.stdout = os.fdopen(read_fd, "rb", buffering=0)
            self.returncode = 0

        def poll(self) -> int:
            return self.returncode

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    def fake_popen(command: list[str], **kwargs: object) -> FakeProcess:
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess(payload)

    monkeypatch.setattr(downloader.subprocess, "Popen", fake_popen)
    output = io.BytesIO()
    count, digest = downloader._stream_gh_api("repos/owner/repo/path", output, 128)
    assert output.getvalue() == payload
    assert count == len(payload)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert captured["command"] == [
        "gh",
        "api",
        "--hostname",
        "github.com",
        "repos/owner/repo/path",
    ]
    assert captured["kwargs"]["stderr"] == subprocess.DEVNULL

    with pytest.raises(downloader.ArtifactDownloadError, match="exceeds its limit"):
        downloader._stream_gh_api("repos/owner/repo/path", io.BytesIO(), 4)


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.txt",
        "/absolute.txt",
        "C:/drive.txt",
        "C:drive-relative.txt",
        r"folder\..\escape.txt",
        "folder/./file.txt",
        "folder//file.txt",
        "folder/../file.txt",
    ],
)
def test_zip_path_validation_rejects_traversal_and_ambiguous_paths(
    member_name: str,
) -> None:
    with pytest.raises(downloader.ArtifactDownloadError, match="unsafe path"):
        downloader._safe_member_path(zipfile.ZipInfo(member_name))


def test_zip_path_validation_bounds_path_size_and_depth() -> None:
    overlong = "a" * (downloader.MAX_ARCHIVE_PATH_BYTES + 1)
    too_deep = "x/" * downloader.MAX_ARCHIVE_PATH_COMPONENTS + "x"
    for member_name in (overlong, too_deep):
        with pytest.raises(downloader.ArtifactDownloadError, match="unsafe path"):
            downloader._safe_member_path(zipfile.ZipInfo(member_name))


def test_zip_path_validation_rejects_nul_symlink_and_special_entries() -> None:
    nul_name = zipfile.ZipInfo("safe.txt")
    nul_name.orig_filename = "safe\x00.txt"
    with pytest.raises(downloader.ArtifactDownloadError, match="unsafe path"):
        downloader._safe_member_path(nul_name)

    symlink = zipfile.ZipInfo("link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(downloader.ArtifactDownloadError, match="special file"):
        downloader._safe_member_path(symlink)

    fifo = zipfile.ZipInfo("pipe")
    fifo.create_system = 3
    fifo.external_attr = (stat.S_IFIFO | 0o600) << 16
    with pytest.raises(downloader.ArtifactDownloadError, match="special file"):
        downloader._safe_member_path(fifo)


@pytest.mark.parametrize(
    "entries",
    [
        [("duplicate.txt", b"one"), ("duplicate.txt", b"two")],
        [("parent/child.txt", b"child"), ("parent", b"file")],
        [("file", b"parent"), ("file/child.txt", b"child")],
    ],
)
def test_zip_validation_rejects_duplicate_and_ancestor_conflicts(
    entries: list[tuple[str, bytes]],
) -> None:
    if entries[0][0] == entries[1][0]:
        with pytest.warns(UserWarning, match="Duplicate name"):
            payload = _zip_bytes(entries)
    else:
        payload = _zip_bytes(entries)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        infos = archive.infolist()
    with pytest.raises(downloader.ArtifactDownloadError):
        downloader._validate_entries(infos, _policy())


def test_zip_validation_indexes_wide_archive_paths_without_pairwise_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TrackedName(str):
        prefix_checks = 0

        def startswith(self, prefix: str, *args: int) -> bool:
            type(self).prefix_checks += 1
            return super().startswith(prefix, *args)

    infos = [
        zipfile.ZipInfo(f"assets/file-{index:05d}.js") for index in range(20_000)
    ]
    monkeypatch.setattr(
        downloader,
        "_safe_member_path",
        lambda info: (TrackedName(info.filename), False),
    )
    records, total_size = downloader._validate_entries(
        infos, _policy(max_entries=20_000)
    )
    assert len(records) == 20_000
    assert total_size == 0
    assert TrackedName.prefix_checks <= 20_000


def test_zip_validation_bounds_entry_and_uncompressed_sizes() -> None:
    with pytest.raises(downloader.ArtifactDownloadError, match="entry count"):
        downloader._validate_entries(
            [zipfile.ZipInfo("one"), zipfile.ZipInfo("two")],
            _policy(max_entries=1),
        )

    infos = [zipfile.ZipInfo("large")]
    infos[0].file_size = 11
    with pytest.raises(downloader.ArtifactDownloadError, match="exceeds its limit"):
        downloader._validate_entries(infos, _policy(max_file_bytes=10))

    infos[0].file_size = 11
    with pytest.raises(downloader.ArtifactDownloadError, match="uncompressed limit"):
        downloader._validate_entries(infos, _policy(max_uncompressed_bytes=10))


def test_zip_extractor_rejects_bounded_central_directory_and_crc_errors(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "archive.zip"
    archive_path.write_bytes(_zip_bytes([("file.txt", b"content")]))
    destination = tmp_path / "stage"
    destination.mkdir()
    with pytest.raises(downloader.ArtifactDownloadError, match="directory exceeds"):
        downloader._extract_zip(
            archive_path,
            destination,
            _policy(max_central_directory_bytes=1),
        )

    raw = bytearray(archive_path.read_bytes())
    raw[raw.find(b"content")] = ord("C")
    corrupt_path = tmp_path / "corrupt.zip"
    corrupt_path.write_bytes(raw)
    with pytest.raises(downloader.ArtifactDownloadError, match="archive is invalid"):
        downloader._extract_zip(corrupt_path, destination, _policy())


def test_destination_validation_refuses_symlinks_and_nonempty_targets(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (target / "preserve.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(downloader.ArtifactDownloadError, match="not empty"):
        downloader._validate_destination(target)
    assert (target / "preserve.txt").read_text(encoding="utf-8") == "keep"

    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(downloader.ArtifactDownloadError, match="symbolic link"):
        downloader._validate_destination(link)

    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(downloader.ArtifactDownloadError, match="parent is unsafe"):
        downloader._validate_destination(linked_parent / "new-target")


def test_download_verifies_digest_before_zip_parse_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner-temp"
    (workspace / "apps" / "frontend").mkdir(parents=True)
    runner_temp.mkdir()
    destination = runner_temp / "backend-image"
    bad_archive = b"not a ZIP archive"
    metadata = _valid_metadata()
    metadata["size_in_bytes"] = len(bad_archive)
    archive_digest = hashlib.sha256(bad_archive).hexdigest()

    def fake_stream(endpoint: str, sink, max_bytes: int) -> tuple[int, str]:
        body = json.dumps(metadata).encode() if not endpoint.endswith("/zip") else bad_archive
        sink.write(body)
        return len(body), hashlib.sha256(body).hexdigest()

    def unexpected_parse(*args: object, **kwargs: object) -> None:
        raise AssertionError("ZIP parsing must not run before digest validation")

    monkeypatch.setattr(downloader, "_stream_gh_api", fake_stream)
    monkeypatch.setattr(downloader, "_extract_zip", unexpected_parse)
    with pytest.raises(downloader.ArtifactDownloadError, match="digest does not match"):
        downloader.download_artifact(
            artifact_id=42,
            name="backend-image-archive",
            upload_digest=DIGEST,
            destination=destination,
            repo="owner/repo",
            run_id=17,
            runner_temp=runner_temp,
            workspace=workspace,
        )
    assert archive_digest != DIGEST
    assert not destination.exists()


def test_download_extracts_only_after_validation_and_preserves_parent_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    runner_temp = tmp_path / "runner-temp"
    frontend_parent = workspace / "apps" / "frontend"
    frontend_parent.mkdir(parents=True)
    runner_temp.mkdir()
    (frontend_parent / "keep.txt").write_text("keep", encoding="utf-8")
    destination = frontend_parent / "dist"
    payload = _zip_bytes([("index.html", b"<html>ok</html>"), ("assets/app.js", b"ok")])
    digest = hashlib.sha256(payload).hexdigest()
    metadata = _valid_metadata(
        name="frontend-release-dist"
    )
    metadata["size_in_bytes"] = len(payload)
    metadata["digest"] = f"sha256:{digest}"
    real_replace = os.replace
    publication: dict[str, bool] = {}

    def record_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        source_path = Path(source)
        target_path = Path(target)
        publication["same_parent_filesystem"] = (
            source_path.parent.parent == target_path.parent
        )
        real_replace(source, target)

    def fake_stream(endpoint: str, sink, max_bytes: int) -> tuple[int, str]:
        body = json.dumps(metadata).encode() if not endpoint.endswith("/zip") else payload
        sink.write(body)
        return len(body), hashlib.sha256(body).hexdigest()

    monkeypatch.setattr(downloader, "_stream_gh_api", fake_stream)
    monkeypatch.setattr(downloader.os, "replace", record_replace)
    downloader.download_artifact(
        artifact_id=42,
        name="frontend-release-dist",
        upload_digest=digest,
        destination=destination,
        repo="owner/repo",
        run_id=17,
        runner_temp=runner_temp,
        workspace=workspace,
    )
    assert (destination / "index.html").read_bytes() == b"<html>ok</html>"
    assert (destination / "assets" / "app.js").read_bytes() == b"ok"
    assert (frontend_parent / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert publication == {"same_parent_filesystem": True}
