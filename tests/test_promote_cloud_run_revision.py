from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def _run_promotion(
    tmp_path: Path,
    *,
    curl_failures: dict[int, int] | None = None,
    curl_statuses: dict[int, int] | None = None,
    marker_missing: bool = False,
    no_marker_counts: set[int] | None = None,
) -> tuple[subprocess.CompletedProcess[str], str, str, str, str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(parents=True)
    gcloud_log = tmp_path / "gcloud.log"
    curl_log = tmp_path / "curl.log"
    curl_count = tmp_path / "curl.count"
    sleep_log = tmp_path / "sleep.log"

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
        "status_for_count() {\n"
        "  local status_count status_value\n"
        "  IFS=',' read -r -a status_overrides <<< \"${CURL_STATUSES:-}\"\n"
        "  for status_override in \"${status_overrides[@]}\"; do\n"
        "    status_count=\"${status_override%%:*}\"\n"
        "    status_value=\"${status_override#*:}\"\n"
        "    if [ \"$1\" = \"$status_count\" ]; then printf '%s' \"$status_value\"; return 0; fi\n"
        "  done\n"
        "  printf '%s' \"$2\"\n"
        "}\n"
        "IFS=',' read -r -a failures <<< \"${CURL_FAILURES:-}\"\n"
        "for failure in \"${failures[@]}\"; do\n"
        "  failure_count=\"${failure%%:*}\"\n"
        "  failure_code=\"${failure#*:}\"\n"
        "  if [ \"$count\" = \"$failure_count\" ]; then\n"
        "    if [ \"$failure_code\" -eq 22 ]; then default_status=403; else default_status=000; fi\n"
        "    printf '\\n%s' \"$(status_for_count \"$count\" \"$default_status\")\"\n"
        "    exit \"$failure_code\"\n"
        "  fi\n"
        "done\n"
        "no_marker=false\n"
        "IFS=',' read -r -a no_marker_counts <<< \"${NO_MARKER_COUNTS:-}\"\n"
        "for no_marker_count in \"${no_marker_counts[@]}\"; do\n"
        "  if [ \"$count\" = \"$no_marker_count\" ]; then no_marker=true; fi\n"
        "done\n"
        "if [ \"${MARKER_MISSING:-false}\" = true ] || [ \"${count}\" -eq 1 ] || [ \"$no_marker\" = true ]; then\n"
        "  body='{\"request_timeout_ms\":120000}'\n"
        "else\n"
        "  body='{\"request_timeout_ms\":120000,\"deployment_version\":\"abc1234\"}'\n"
        "fi\n"
        "printf '%s\\n%s' \"$body\" \"$(status_for_count \"$count\" 200)\"\n",
        encoding="utf-8",
    )
    (fake_bin / "sleep").write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"${SLEEP_LOG}\"\n",
        encoding="utf-8",
    )
    for command in (fake_bin / "gcloud", fake_bin / "curl", fake_bin / "sleep"):
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
        "CURL_FAILURES": ",".join(f"{count}:{code}" for count, code in (curl_failures or {}).items()),
        "CURL_STATUSES": ",".join(f"{count}:{status}" for count, status in (curl_statuses or {}).items()),
        "MARKER_MISSING": str(marker_missing).lower(),
        "NO_MARKER_COUNTS": ",".join(str(count) for count in (no_marker_counts or set())),
        "SLEEP_LOG": str(sleep_log),
        "SERVICE_JSON": service_json,
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
            "--requests-per-attempt",
            "2",
            "--health-url",
            "https://production.example.test/api/config",
            "--expected-version",
            "abc1234",
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
        curl_count.read_text(encoding="utf-8") if curl_count.exists() else "0",
        sleep_log.read_text(encoding="utf-8") if sleep_log.exists() else "",
    )


def test_promotes_healthy_candidate_after_canary_window(tmp_path: Path) -> None:
    proc, gcloud_log, curl_log, curl_count, _ = _run_promotion(tmp_path)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--to-tags candidate=10" in gcloud_log
    assert "--to-tags candidate=100" in gcloud_log
    assert "--to-revisions" not in gcloud_log
    assert curl_log.count("https://production.example.test/api/config?deployment_probe=") == 5
    assert "Cache-Control: no-cache" in curl_log
    assert "--write-out" in curl_log
    assert curl_count == "5"


def test_restores_previous_traffic_when_canary_health_fails(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, _ = _run_promotion(tmp_path, curl_failures={1: 22})

    assert proc.returncode != 0
    assert "--to-tags candidate=10" in gcloud_log
    assert "--to-tags candidate=100" not in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "Previous traffic allocation restored" in proc.stdout
    assert "curl exit 22; HTTP 403" in proc.stderr
    assert "Retrying transient" not in proc.stdout
    assert curl_count == "1"


def test_retries_transport_failure_then_promotes_expected_marker(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, sleep_log = _run_promotion(tmp_path, curl_failures={1: 28})

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--to-tags candidate=100" in gcloud_log
    assert curl_count == "6"
    assert sleep_log.splitlines().count("2") == 1
    assert "HTTP 000" in proc.stdout
    assert "curl exit 28" in proc.stdout


def test_exhausted_transport_retry_budget_restores_previous_traffic(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, sleep_log = _run_promotion(
        tmp_path, curl_failures={1: 28, 2: 28, 3: 28}
    )

    assert proc.returncode != 0
    assert "--to-tags candidate=100" not in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "curl exit 28; HTTP 000" in proc.stderr
    assert curl_count == "3"
    assert sleep_log.splitlines() == ["2", "4"]


def test_transport_retry_budget_is_shared_with_postpromotion_check(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, sleep_log = _run_promotion(
        tmp_path, curl_failures={1: 28, 6: 28, 8: 28}, no_marker_counts={7}
    )

    assert proc.returncode != 0
    assert "--to-tags candidate=100" in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "curl exit 28; HTTP 000" in proc.stderr
    assert curl_count == "8"
    assert sleep_log.splitlines() == ["2", "0", "4", "1"]


def test_nonretryable_tls_failure_restores_previous_traffic_immediately(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, sleep_log = _run_promotion(tmp_path, curl_failures={1: 60})

    assert proc.returncode != 0
    assert "--to-tags candidate=100" not in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "curl exit 60; HTTP 000" in proc.stderr
    assert "Retrying transient" not in proc.stdout
    assert curl_count == "1"
    assert sleep_log == ""


def test_http_error_status_precedes_curl_exit_code(tmp_path: Path) -> None:
    scenarios = (
        ("unauthorized", {}, {1: 401}),
        ("forbidden", {}, {1: 403}),
        ("server_error", {1: 28}, {1: 503}),
    )
    for name, curl_failures, curl_statuses in scenarios:
        proc, gcloud_log, _, curl_count, sleep_log = _run_promotion(
            tmp_path / name,
            curl_failures=curl_failures,
            curl_statuses=curl_statuses,
        )

        assert proc.returncode != 0
        assert "--to-tags candidate=100" not in gcloud_log
        assert "--to-revisions wordpack-backend-old=100" in gcloud_log
        assert "Production health request failed" in proc.stderr
        assert f"HTTP {curl_statuses[1]}" in proc.stderr
        assert "Retrying transient" not in proc.stdout
        assert curl_count == "1"
        assert sleep_log == ""


def test_missing_expected_marker_still_restores_previous_traffic(tmp_path: Path) -> None:
    proc, gcloud_log, _, curl_count, _ = _run_promotion(tmp_path, marker_missing=True)

    assert proc.returncode != 0
    assert "--to-tags candidate=100" not in gcloud_log
    assert "--to-revisions wordpack-backend-old=100" in gcloud_log
    assert "Canary traffic did not return the expected deployment version" in proc.stderr
    assert curl_count == "4"
