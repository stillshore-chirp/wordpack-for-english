from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def test_deploy_script_requires_firestore_project_id_or_gcp_project_id() -> None:
    """デプロイスクリプトが Firestore 接続用プロジェクト ID の pre-flight チェックを持つことを確認。

    バックエンド config.py と同じエイリアス（FIRESTORE_PROJECT_ID, GCP_PROJECT_ID,
    GOOGLE_CLOUD_PROJECT, PROJECT_ID）を許容するチェックが存在することを検証する。
    """
    text = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    # 派生ロジックが存在すること
    assert "FIRESTORE_PROJECT_ID:-${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID" in text
    # エラーメッセージに全エイリアスが列挙されていること
    assert "FIRESTORE_PROJECT_ID, GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or PROJECT_ID" in text


def test_deploy_script_supports_cloud_run_min_instances() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")
    ci_workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    dry_run_workflow = Path(".github/workflows/deploy-dry-run.yml").read_text(encoding="utf-8")
    production_workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    deploy_env_example = Path("env.deploy.example").read_text(encoding="utf-8")

    assert "--min-instances <count>" in deploy_script
    assert "CLOUD_RUN_MIN_INSTANCES: 例 0, 1, default" in deploy_script
    assert 'RUN_ARGS+=(--min "$MIN_INSTANCES")' in deploy_script
    assert "$(if $(MIN_INSTANCES),--min-instances $(MIN_INSTANCES),)" in makefile
    assert "--min-instances 1" in ci_workflow
    assert 'CLOUD_RUN_MIN_INSTANCES: "1"' in dry_run_workflow
    assert "MIN_INSTANCES=${{ env.CLOUD_RUN_MIN_INSTANCES }}" in dry_run_workflow
    assert "CLOUD_RUN_MIN_INSTANCES: ${{ vars.CLOUD_RUN_MIN_INSTANCES || '1' }}" in production_workflow
    assert 'MIN_INSTANCES="${CLOUD_RUN_MIN_INSTANCES}"' in production_workflow
    assert "CLOUD_RUN_MIN_INSTANCES=1" in deploy_env_example


def test_deploy_script_rejects_invalid_cloud_run_min_instances() -> None:
    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--dry-run",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--service",
            "wordpack-backend",
            "--min-instances",
            "one",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    combined_output = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "Cloud Run minimum instances must be a non-negative integer or 'default'" in combined_output
    assert "Validating backend settings" not in combined_output


def test_deploy_script_supports_tagged_no_traffic_candidates() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "--no-traffic" in deploy_script
    assert "--traffic-tag <tag>" in deploy_script
    assert 'RUN_ARGS+=(--no-traffic)' in deploy_script
    assert 'RUN_ARGS+=(--tag "$TRAFFIC_TAG")' in deploy_script
    assert "$(if $(filter true,$(NO_TRAFFIC)),--no-traffic,)" in makefile
    assert "$(if $(TRAFFIC_TAG),--traffic-tag $(TRAFFIC_TAG),)" in makefile
    assert 'DEPLOYMENT_VERSION="$IMAGE_TAG"' in deploy_script
    assert 'add_env_key "DEPLOYMENT_VERSION"' in deploy_script


def test_deploy_script_requires_a_tag_for_no_traffic_mode() -> None:
    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--dry-run",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--no-traffic",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode != 0
    assert "--no-traffic requires --traffic-tag" in proc.stdout + proc.stderr


def test_release_cloud_run_stops_when_index_sync_fails(tmp_path: Path) -> None:
    fake_cloud_run = tmp_path / "fake_cloud_run.sh"
    fake_cloud_run.write_text(
        "#!/usr/bin/env bash\n"
        "echo CLOUD_RUN_SCRIPT_RAN\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_cloud_run.chmod(0o755)

    proc = subprocess.run(
        [
            "make",
            "-s",
            "release-cloud-run",
            "PROJECT_ID=demo-project",
            "REGION=asia-northeast1",
            "ENV_FILE=configs/cloud-run/ci.env",
            "TOOL=invalid",
            f"CLOUD_RUN_SCRIPT={fake_cloud_run}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    combined_output = proc.stdout + proc.stderr

    assert proc.returncode != 0
    assert "--tool には gcloud または firebase を指定してください" in combined_output
    assert "CLOUD_RUN_SCRIPT_RAN" not in combined_output


class _FirestoreAdminApiHandler(BaseHTTPRequestHandler):
    requests: list[dict[str, object]] = []

    def _record(self, status: int, payload: dict[str, object]) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        self.requests.append(
            {
                "method": self.command,
                "path": self.path,
                "authorization": self.headers.get("Authorization"),
                "body": json.loads(body) if body else {},
            }
        )
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self) -> None:
        self._record(
            409,
            {"error": {"status": "ALREADY_EXISTS", "message": "index already exists"}},
        )

    def do_PATCH(self) -> None:
        self._record(200, {"name": "operations/mock"})

    def log_message(self, format: str, *args: object) -> None:
        return


def test_gcloud_index_sync_uses_firestore_admin_api_for_indexes_and_field_overrides(tmp_path: Path) -> None:
    _FirestoreAdminApiHandler.requests = []
    server = HTTPServer(("127.0.0.1", 0), _FirestoreAdminApiHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gcloud_log = tmp_path / "gcloud.log"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [ \"$1\" = \"auth\" ] && [ \"$2\" = \"print-access-token\" ]; then\n"
        "  printf 'fake-token\\n'\n"
        "  exit 0\n"
        "fi\n"
        "printf 'unexpected gcloud command: %s\\n' \"$*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)

    index_file = tmp_path / "firestore.indexes.json"
    index_file.write_text(
        """{
  "indexes": [
    {
      "collectionGroup": "examples",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "category", "order": "ASCENDING" },
        { "fieldPath": "created_at", "order": "DESCENDING" }
      ]
    }
  ],
  "fieldOverrides": [
    {
      "collectionGroup": "lemmas",
      "fieldPath": "normalized_label",
      "indexes": [
        { "order": "ASCENDING", "queryScope": "COLLECTION" }
      ]
    }
  ]
}
""",
        encoding="utf-8",
    )

    try:
        proc = subprocess.run(
            [
                "scripts/deploy_firestore_indexes.sh",
                "--project",
                "demo-project",
                "--tool",
                "gcloud",
                "--index-file",
                str(index_file),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PATH": f"{fake_bin}:{os.environ['PATH']}",
                "FIRESTORE_ADMIN_API_BASE_URL": f"http://127.0.0.1:{server.server_port}/v1",
                "GCLOUD_LOG": str(gcloud_log),
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    combined_output = proc.stdout + proc.stderr
    assert proc.returncode == 0, combined_output
    assert "既存のためスキップ" in combined_output
    assert "fieldOverride 同期済み" in combined_output

    calls = gcloud_log.read_text(encoding="utf-8").splitlines()
    assert calls == ["auth print-access-token --quiet"]
    assert "alpha" not in "\n".join(calls)

    requests = _FirestoreAdminApiHandler.requests
    assert [request["method"] for request in requests] == ["POST", "PATCH"]
    assert requests[0]["authorization"] == "Bearer fake-token"
    assert requests[1]["authorization"] == "Bearer fake-token"
    assert requests[0]["path"] == (
        "/v1/projects/demo-project/databases/%28default%29/"
        "collectionGroups/examples/indexes"
    )
    assert requests[1]["path"] == (
        "/v1/projects/demo-project/databases/%28default%29/"
        "collectionGroups/lemmas/fields/normalized_label?updateMask=indexConfig"
    )

    composite_body = requests[0]["body"]
    assert composite_body == {
        "queryScope": "COLLECTION",
        "fields": [
            {"fieldPath": "category", "order": "ASCENDING"},
            {"fieldPath": "created_at", "order": "DESCENDING"},
        ],
    }

    field_override_body = requests[1]["body"]
    assert field_override_body == {
        "name": (
            "projects/demo-project/databases/(default)/"
            "collectionGroups/lemmas/fields/normalized_label"
        ),
        "indexConfig": {
            "indexes": [
                {
                    "queryScope": "COLLECTION",
                    "fields": [{"fieldPath": "normalized_label", "order": "ASCENDING"}],
                }
            ]
        },
    }
