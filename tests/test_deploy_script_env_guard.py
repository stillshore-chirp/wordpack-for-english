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
    production_workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    deploy_env_example = Path("env.deploy.example").read_text(encoding="utf-8")

    assert "--min-instances <count>" in deploy_script
    assert "CLOUD_RUN_MIN_INSTANCES: 例 0, 1, default" in deploy_script
    assert 'RUN_ARGS+=(--min "$MIN_INSTANCES")' in deploy_script
    assert "$(if $(MIN_INSTANCES),--min-instances $(MIN_INSTANCES),)" in makefile
    assert not Path(".github/workflows/deploy-dry-run.yml").exists()
    assert "deploy_preflight:" in ci_workflow
    assert "name: Static deploy preflight" in ci_workflow
    assert "shellcheck" in ci_workflow
    for script_path in (
        "scripts/build_backend_artifact.sh",
        "scripts/verify_backend_artifact_attestations.sh",
        "scripts/deploy_cloud_run.sh",
        "scripts/promote_cloud_run_revision.sh",
    ):
        assert script_path in ci_workflow
    assert "./scripts/deploy_cloud_run.sh --dry-run" in ci_workflow
    assert "--min-instances 1" in ci_workflow
    assert "--no-traffic --traffic-tag candidate" in ci_workflow
    assert "CLOUD_RUN_MIN_INSTANCES: ${{ vars.CLOUD_RUN_MIN_INSTANCES || '1' }}" in production_workflow
    assert 'MIN_INSTANCES="${CLOUD_RUN_MIN_INSTANCES}"' in production_workflow
    assert "CLOUD_RUN_MIN_INSTANCES=1" in deploy_env_example


def test_deploy_script_applies_no_cpu_throttling_from_env_file() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    deploy_env_example = Path("env.deploy.example").read_text(encoding="utf-8")

    assert 'NO_CPU_THROTTLING_ARG=""' in deploy_script
    assert (
        'NO_CPU_THROTTLING="${NO_CPU_THROTTLING_ARG:-'
        '${CLOUD_RUN_NO_CPU_THROTTLING:-false}}"'
    ) in deploy_script
    assert 'RUN_ARGS+=(--no-cpu-throttling)' in deploy_script
    assert "CLOUD_RUN_NO_CPU_THROTTLING=true" in deploy_env_example


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
            "--image-uri",
            "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@sha256:" + "0" * 64,
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
    assert 'DEPLOYMENT_VERSION="${DEPLOYMENT_VERSION:-$CHECKED_OUT_SHA}"' in deploy_script
    assert 'add_env_key "DEPLOYMENT_VERSION"' in deploy_script


def test_deploy_script_consumes_only_an_immutable_image_uri() -> None:
    """The helper is a digest-only deploy boundary; build stays in the workflow."""
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "--image-uri" in deploy_script
    assert "@sha256:" in deploy_script
    assert "gcloud builds submit" not in deploy_script
    assert "IMAGE_URI" in makefile
    assert "--image-uri" in makefile
    assert "GCP_SA_KEY" not in deploy_script
    assert "credentials_json" not in deploy_script


def test_release_cloud_run_validates_full_image_uri_before_firestore_sync() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    validation_index = makefile.index("EXPECTED_IMAGE_NAME")
    dry_run_index = makefile.index('echo "[release-cloud-run] Validating Cloud Run configuration via dry-run"')
    firestore_index = makefile.index('echo "[release-cloud-run] Syncing Firestore indexes')
    assert validation_index < dry_run_index < firestore_index
    assert 'IMAGE_DIGEST_VALUE="$${IMAGE_URI_VALUE##*@}"' in makefile
    assert "sha256:[0-9a-f]{64}" in makefile


def test_deploy_script_documents_digest_and_repository_fail_closed_checks() -> None:
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    lowered = deploy_script.lower()

    assert "sha256" in lowered
    assert "project" in lowered
    assert "repository" in lowered or "artifact" in lowered
    assert "must" in lowered or "invalid" in lowered
    assert "exit 1" in deploy_script


def test_deploy_script_validates_settings_inside_exact_image(tmp_path: Path) -> None:
    """Production validation uses the pulled digest, without host dependency installs."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    docker_log = tmp_path / "docker.log"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%q ' \"$@\" >> \"${DOCKER_LOG}\"\n"
        "printf '\\n' >> \"${DOCKER_LOG}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    image_uri = "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@sha256:" + "0" * 64

    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--dry-run",
            "--validate-in-image",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--image-uri",
            image_uri,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "DOCKER_LOG": str(docker_log),
        },
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = docker_log.read_text(encoding="utf-8")
    assert f"pull --quiet {image_uri}" in calls
    assert "run --rm --env-file configs/cloud-run/ci.env" in calls
    assert "--env PROJECT_ID=ci-placeholder-project" in calls
    assert "--env GIT_SHA=" in calls
    assert "--env DEPLOYMENT_VERSION=" in calls
    assert f"{image_uri} python -m apps.backend.backend.config" in calls
    assert "Validating backend settings via" not in proc.stdout + proc.stderr


def test_deploy_script_fails_closed_when_in_image_validation_fails(tmp_path: Path) -> None:
    """A container validation error stops both dry-run and the deploy path."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [ \"$1\" = run ]; then exit 1; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    for dry_run in (True, False):
        command = [
            "scripts/deploy_cloud_run.sh",
            "--validate-in-image",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--image-uri",
            "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@sha256:" + "0" * 64,
        ]
        if dry_run:
            command.insert(1, "--dry-run")
        proc = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )

        combined_output = proc.stdout + proc.stderr
        assert proc.returncode != 0
        assert "Backend configuration validation failed inside the exact image" in combined_output
        assert "Dry run mode" not in combined_output


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
            "--image-uri",
            "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@sha256:" + "0" * 64,
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
                "IMAGE_URI=asia-northeast1-docker.pkg.dev/demo-project/wordpack/backend@sha256:" + "0" * 64,
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


def test_release_cloud_run_rejects_invalid_image_before_index_side_effect(tmp_path: Path) -> None:
    fake_cloud_run = tmp_path / "fake_cloud_run.sh"
    fake_cloud_run.write_text(
        "#!/usr/bin/env bash\n"
        "echo CLOUD_RUN_SCRIPT_RAN\n"
        "touch \"${DEPLOY_MARKER}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_cloud_run.chmod(0o755)
    deploy_marker = tmp_path / "deploy-marker"
    invalid_images = (
        "asia-northeast1-docker.pkg.dev/other-project/wordpack/backend@sha256:" + "0" * 64,
        "asia-northeast1-docker.pkg.dev/demo-project/wordpack/backend:target",
        "asia-northeast1-docker.pkg.dev/demo-project/wordpack/backend@sha256:" + "0" * 63,
    )

    for image_uri in invalid_images:
        proc = subprocess.run(
            [
                "make",
                "-s",
                "release-cloud-run",
                "PROJECT_ID=demo-project",
                "REGION=asia-northeast1",
                "ENV_FILE=configs/cloud-run/ci.env",
                f"IMAGE_URI={image_uri}",
                "TOOL=invalid",
                f"CLOUD_RUN_SCRIPT={fake_cloud_run}",
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "DEPLOY_MARKER": str(deploy_marker)},
        )
        combined_output = proc.stdout + proc.stderr
        assert proc.returncode != 0
        assert "IMAGE_URI must exactly match" in combined_output
        assert "Syncing Firestore indexes" not in combined_output
        assert "--tool には gcloud または firebase を指定してください" not in combined_output
        assert "CLOUD_RUN_SCRIPT_RAN" not in combined_output
        assert not deploy_marker.exists()


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
