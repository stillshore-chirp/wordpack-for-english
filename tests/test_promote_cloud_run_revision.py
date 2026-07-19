from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_promotion(tmp_path: Path, *, fail_after_canary: bool = False) -> tuple[subprocess.CompletedProcess[str], str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gcloud_log = tmp_path / "gcloud.log"
    curl_log = tmp_path / "curl.log"
    curl_count = tmp_path / "curl.count"

    (fake_bin / "gcloud").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [ \"$1 $2 $3\" = \"run services describe\" ]; then\n"
        "  printf '%s\\n' \"${SERVICE_JSON}\"\n"
        "fi\n",
        encoding="utf-8",
    )
    (fake_bin / "curl").write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "count=0\n"
        "if [ -f \"${CURL_COUNT}\" ]; then count=$(cat \"${CURL_COUNT}\"); fi\n"
        "count=$((count + 1))\n"
        "printf '%s' \"${count}\" > \"${CURL_COUNT}\"\n"
        "printf '%s\\n' \"$*\" >> \"${CURL_LOG}\"\n"
        "if [ \"${FAIL_AFTER_CANARY:-false}\" = true ] && [ \"${count}\" -ge 2 ]; then\n"
        "  printf '503'\n"
        "else\n"
        "  printf '200'\n"
        "fi\n",
        encoding="utf-8",
    )
    for command in (fake_bin / "gcloud", fake_bin / "curl"):
        command.chmod(0o755)

    service_json = json.dumps(
        {
            "status": {
                "traffic": [
                    {"revisionName": "wordpack-backend-old", "percent": 100},
                    {
                        "revisionName": "wordpack-backend-new",
                        "tag": "candidate",
                        "url": "https://candidate.example.test",
                    },
                ]
            }
        }
    )
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GCLOUD_LOG": str(gcloud_log),
        "CURL_LOG": str(curl_log),
        "CURL_COUNT": str(curl_count),
        "SERVICE_JSON": service_json,
        "FAIL_AFTER_CANARY": str(fail_after_canary).lower(),
    }
    proc = subprocess.run(
        [
            "scripts/promote_cloud_run_revision.sh",
            "--project-id",
            "test-project",
            "--region",
            "asia-northeast1",
            "--service",
            "wordpack-backend",
            "--tag",
            "candidate",
            "--canary-percent",
            "10",
            "--attempts",
            "2",
            "--delay-seconds",
            "0",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    return (
        proc,
        gcloud_log.read_text(encoding="utf-8") if gcloud_log.exists() else "",
        curl_log.read_text(encoding="utf-8") if curl_log.exists() else "",
    )


def test_promotes_healthy_candidate_after_canary_window(tmp_path: Path) -> None:
    proc, gcloud_log, curl_log = _run_promotion(tmp_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--to-tags candidate=10" in gcloud_log
    assert "--to-tags candidate=100" in gcloud_log
    assert "--to-revisions" not in gcloud_log
    assert curl_log.count("https://candidate.example.test/healthz") == 3


def test_restores_previous_traffic_when_canary_health_fails(tmp_path: Path) -> None:
    proc, gcloud_log, _ = _run_promotion(tmp_path, fail_after_canary=True)

    assert proc.returncode != 0
    assert "--to-tags candidate=10" in gcloud_log
    assert "--to-tags candidate=100" not in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "Previous traffic allocation restored" in proc.stdout
