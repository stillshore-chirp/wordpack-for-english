from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class _HostingApiHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def _record(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b""
        parsed = urlparse(self.path)
        content_type = self.headers.get("Content-Type", "")
        if raw_body and "application/json" in content_type:
            body: object = json.loads(raw_body.decode("utf-8"))
        else:
            body = raw_body
        record = {
            "method": self.command,
            "path": parsed.path,
            "query": parse_qs(parsed.query),
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        self.requests.append(record)
        return record

    def _send_json(self, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        record = self._record()
        if record["path"] == "/v1beta1/sites/demo-project/versions":
            self._send_json({"name": "sites/demo-project/versions/version-1"})
            return
        if record["path"] == "/v1beta1/sites/demo-project/versions/version-1:populateFiles":
            files = record["body"]["files"]  # type: ignore[index]
            self._send_json(
                {
                    "uploadUrl": f"http://127.0.0.1:{self.server.server_port}/upload",
                    "uploadRequiredHashes": list(files.values()),
                }
            )
            return
        if record["path"].startswith("/upload/"):
            self._send_json({})
            return
        if record["path"] == "/v1beta1/sites/demo-project/releases":
            self._send_json({"name": "release-1"})
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        self._record()
        self._send_json({"name": "projects/-/sites/demo-project/versions/version-1"})

    def do_GET(self) -> None:
        record = self._record()
        if record["path"] == "/v1beta1/sites/demo-project/releases":
            self._send_json({"releases": []})
            return
        self.send_error(404)

    def log_message(self, format: str, *args: object) -> None:
        return


def _write_hosting_fixture(tmp_path: Path) -> Path:
    public_dir = tmp_path / "dist"
    public_dir.mkdir()
    (public_dir / "index.html").write_text("<div>ok</div>", encoding="utf-8")
    assets_dir = public_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "app.js").write_text("console.log('ok')\n", encoding="utf-8")

    config_path = tmp_path / "firebase.json"
    config_path.write_text(
        json.dumps(
            {
                "hosting": {
                    "public": str(public_dir),
                    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
                    "rewrites": [
                        {
                            "source": "/api/**",
                            "run": {"serviceId": "wordpack-backend", "region": "asia-northeast1"},
                        },
                        {"source": "**", "destination": "/index.html"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return config_path


def _write_fake_gcloud(tmp_path: Path, exit_status: int = 0) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gcloud_log = tmp_path / "gcloud.log"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"print-access-token\" ]; then\n"
        f"  exit_status={exit_status}\n"
        "  if [ \"$exit_status\" -eq 0 ]; then\n"
        "    printf 'fake-hosting-token\\n'\n"
        "  else\n"
        "    printf 'unexpected gcloud call\\n' >&2\n"
        "  fi\n"
        "  exit \"$exit_status\"\n"
        "fi\n"
        "printf 'unexpected gcloud command: %s\\n' \"$*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)
    return fake_bin, gcloud_log


def test_deploy_firebase_hosting_uses_hosting_api_and_gcloud_token(tmp_path: Path) -> None:
    _HostingApiHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _HostingApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    config_path = _write_hosting_fixture(tmp_path)
    fake_bin, gcloud_log = _write_fake_gcloud(tmp_path)

    try:
        proc = subprocess.run(
            [
                "python",
                "scripts/deploy_firebase_hosting.py",
                "--project",
                "demo-project",
                "--site",
                "demo-project",
                "--config",
                str(config_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "GCLOUD_LOG": str(gcloud_log),
                "FIREBASE_HOSTING_API_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1beta1",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert gcloud_log.read_text(encoding="utf-8").splitlines() == ["auth print-access-token --quiet"]

    requests = _HostingApiHandler.requests
    assert [request["method"] for request in requests] == ["POST", "POST", "POST", "POST", "PATCH", "POST"]
    assert all(request["authorization"] == "Bearer fake-hosting-token" for request in requests)
    assert requests[1]["body"]["files"].keys() == {"/assets/app.js", "/index.html"}  # type: ignore[index, union-attr]
    assert requests[4]["path"] == "/v1beta1/sites/demo-project/versions/version-1"
    assert requests[4]["query"] == {"update_mask": ["status,config"]}
    assert requests[4]["body"]["config"] == {  # type: ignore[index]
        "rewrites": [
            {
                "glob": "/api/**",
                "run": {"serviceId": "wordpack-backend", "region": "asia-northeast1"},
            },
            {"glob": "**", "path": "/index.html"},
        ]
    }
    assert requests[5]["path"] == "/v1beta1/sites/demo-project/releases"
    assert requests[5]["query"] == {"versionName": ["sites/demo-project/versions/version-1"]}


def test_deploy_firebase_hosting_plan_only_does_not_call_gcloud_or_api(tmp_path: Path) -> None:
    config_path = _write_hosting_fixture(tmp_path)
    fake_bin, gcloud_log = _write_fake_gcloud(tmp_path, exit_status=2)

    proc = subprocess.run(
        [
            "python",
            "scripts/deploy_firebase_hosting.py",
            "--project",
            "demo-project",
            "--site",
            "demo-project",
            "--config",
            str(config_path),
            "--plan-only",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "GCLOUD_LOG": str(gcloud_log),
            "FIREBASE_HOSTING_API_BASE_URL": "http://127.0.0.1:9/v1beta1",
        },
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not gcloud_log.exists()
    assert "Plan-only preflight complete" in proc.stdout
    assert "POST /sites/demo-project/versions" in proc.stdout
    assert "PATCH /sites/demo-project/versions/{versionId}?update_mask=status,config" in proc.stdout


def test_deploy_firebase_hosting_probe_only_uses_read_only_releases_list(tmp_path: Path) -> None:
    _HostingApiHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _HostingApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    config_path = _write_hosting_fixture(tmp_path)
    fake_bin, gcloud_log = _write_fake_gcloud(tmp_path)

    try:
        proc = subprocess.run(
            [
                "python",
                "scripts/deploy_firebase_hosting.py",
                "--project",
                "demo-project",
                "--site",
                "demo-project",
                "--config",
                str(config_path),
                "--probe-only",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "GCLOUD_LOG": str(gcloud_log),
                "FIREBASE_HOSTING_API_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1beta1",
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert gcloud_log.read_text(encoding="utf-8").splitlines() == ["auth print-access-token --quiet"]
    assert "Probe-only preflight complete" in proc.stdout
    assert _HostingApiHandler.requests == [
        {
            "method": "GET",
            "path": "/v1beta1/sites/demo-project/releases",
            "query": {"pageSize": ["1"]},
            "authorization": "Bearer fake-hosting-token",
            "body": b"",
        }
    ]
