from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import yaml

def test_cloud_build_has_backend_config_and_deploy_script_uses_it() -> None:
    """
    Contract: Cloud Build must not rely on a repo-root Dockerfile being present in the remote workspace.
    We keep a dedicated Cloud Build config that explicitly uses Dockerfile.backend, and the deploy script
    must submit builds with --config to avoid 'Dockerfile: no such file or directory' failures.
    """

    config_path = Path("cloudbuild.backend.yaml")
    assert config_path.exists(), "cloudbuild.backend.yaml must exist for Cloud Build backend image"

    config_text = config_path.read_text(encoding="utf-8")
    assert "Dockerfile.backend" in config_text, "cloudbuild.backend.yaml must reference Dockerfile.backend"
    assert "_IMAGE_URI" in config_text, "cloudbuild.backend.yaml must accept _IMAGE_URI substitution"

    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert (
        "cloudbuild.backend.yaml" in deploy_script
    ), "deploy_cloud_run.sh must use cloudbuild.backend.yaml via --config"


def test_cloud_build_uses_explicit_dedicated_service_account_and_cloud_logging() -> None:
    """Static and generated build configs must support a custom build service account."""
    config_path = Path("cloudbuild.backend.yaml")
    config_text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)

    assert isinstance(config, dict)
    assert config["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    assert "options:" in config_text
    assert "logging: CLOUD_LOGGING_ONLY" in config_text

    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "--build-service-account <email>" in deploy_script
    assert 'BUILD_SA="$BUILD_SERVICE_ACCOUNT_ARG"' in deploy_script
    assert r"@${PROJECT_ID}\.iam\.gserviceaccount\.com" in deploy_script
    assert '"--service-account=projects/${PROJECT_ID}/serviceAccounts/${BUILD_SA}"' in deploy_script
    assert "echo \"  logging: CLOUD_LOGGING_ONLY\"" in deploy_script

    deployment_docs = Path("docs/deployment.md").read_text(encoding="utf-8")
    deploy_roles_start = deployment_docs.index("production deploy service account に必要な代表ロール:")
    build_roles_start = deployment_docs.index("dedicated Cloud Build service account に必要な代表ロール:")
    deploy_roles = deployment_docs[deploy_roles_start:build_roles_start]
    build_roles_end = deployment_docs.index("authenticated preflight service account は次の read-only role に限定します。", build_roles_start)
    build_roles = deployment_docs[build_roles_start:build_roles_end]
    assert "roles/artifactregistry.reader" in deploy_roles
    assert "roles/artifactregistry.writer" not in deploy_roles
    assert "roles/serviceusage.serviceUsageConsumer" in deploy_roles
    assert "roles/serviceusage.serviceUsageViewer" not in deploy_roles
    assert "roles/serviceusage.serviceUsageAdmin" not in deploy_roles
    assert "serviceusage.services.use" in deploy_roles
    assert "roles/artifactregistry.writer" in build_roles


def test_generated_cloud_build_config_keeps_custom_sa_logging_option(tmp_path: Path) -> None:
    """The --build-arg path must emit the same logging contract as the static config."""
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    captured_config = tmp_path / "captured-build.yaml"
    gcloud_log = tmp_path / "gcloud.log"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [[ \"${1:-}\" == builds && \"${2:-}\" == submit ]]; then\n"
        "  previous=''\n"
        "  for argument in \"$@\"; do\n"
        "    if [[ \"${previous}\" == --config ]]; then\n"
        "      cp \"${argument}\" \"${CAPTURED_CONFIG}\"\n"
        "      exit 0\n"
        "    fi\n"
        "    previous=\"${argument}\"\n"
        "  done\n"
        "  echo 'missing --config' >&2\n"
        "  exit 2\n"
        "fi\n"
        "if [[ \"${1:-}\" == run && \"${2:-}\" == deploy ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "echo \"unexpected gcloud command: $*\" >&2\n"
        "exit 2\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)

    build_service_account = "build-sa@ci-placeholder-project.iam.gserviceaccount.com"
    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--build-service-account",
            build_service_account,
            "--build-arg",
            "EXAMPLE_BUILD_ARG=contract-test",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DISABLE_SESSION_AUTH": "false",
            "SKIP_FIRESTORE_INDEX_SYNC": "true",
            "CAPTURED_CONFIG": str(captured_config),
            "GCLOUD_LOG": str(gcloud_log),
        },
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated_text = captured_config.read_text(encoding="utf-8")
    generated = yaml.safe_load(generated_text)
    assert isinstance(generated, dict)
    assert generated["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    assert "EXAMPLE_BUILD_ARG=contract-test" in generated_text

    gcloud_calls = gcloud_log.read_text(encoding="utf-8")
    assert (
        "--service-account=projects/ci-placeholder-project/serviceAccounts/"
        f"{build_service_account}"
    ) in gcloud_calls
    assert "credentials" not in (proc.stdout + proc.stderr).lower()
    assert "token" not in (proc.stdout + proc.stderr).lower()


def test_real_cloud_build_requires_explicit_service_account(tmp_path: Path) -> None:
    """A real submission must fail closed before any Cloud Build side effect without the SA."""
    invocation_marker = tmp_path / "gcloud-invoked"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "touch \"${INVOCATION_MARKER}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)

    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "DISABLE_SESSION_AUTH": "false",
            "SKIP_FIRESTORE_INDEX_SYNC": "true",
            "INVOCATION_MARKER": str(invocation_marker),
        },
    )

    assert proc.returncode != 0
    assert "--build-service-account is required for Cloud Build submissions" in proc.stderr
    assert not invocation_marker.exists()


def test_cleanup_temp_files_handles_all_file_states_and_preserves_failure_status(tmp_path: Path) -> None:
    """The EXIT cleanup must be status-neutral on success and preserve failures."""
    script_text = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    match = re.search(
        r"cleanup_temp_files\(\) \{\n(?P<body>.*?)\n\}\ntrap cleanup_temp_files EXIT",
        script_text,
        flags=re.DOTALL,
    )
    assert match is not None
    cleanup_function = "cleanup_temp_files() {\n" + match.group("body") + "\n}"

    harness = f"""#!/usr/bin/env bash
set -euo pipefail
{cleanup_function}

GENERATED_BUILDCONFIG=""
ENV_VARS_FILE=""
cleanup_temp_files

GENERATED_BUILDCONFIG="{tmp_path}/generated.yaml"
touch "$GENERATED_BUILDCONFIG"
ENV_VARS_FILE=""
cleanup_temp_files
[[ ! -e "$GENERATED_BUILDCONFIG" ]]

GENERATED_BUILDCONFIG=""
ENV_VARS_FILE="{tmp_path}/env.yaml"
touch "$ENV_VARS_FILE"
cleanup_temp_files
[[ ! -e "$ENV_VARS_FILE" ]]

GENERATED_BUILDCONFIG="{tmp_path}/generated-both.yaml"
ENV_VARS_FILE="{tmp_path}/env-both.yaml"
touch "$GENERATED_BUILDCONFIG" "$ENV_VARS_FILE"
cleanup_temp_files
[[ ! -e "$GENERATED_BUILDCONFIG" && ! -e "$ENV_VARS_FILE" ]]

GENERATED_BUILDCONFIG=""
ENV_VARS_FILE=""
set +e
false
cleanup_temp_files
failure_status=$?
set -e
[[ "$failure_status" -eq 1 ]]
"""
    harness_path = tmp_path / "cleanup-harness.sh"
    harness_path.write_text(harness, encoding="utf-8")
    harness_path.chmod(0o755)

    proc = subprocess.run([str(harness_path)], check=False, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_build_service_account_must_belong_to_project() -> None:
    """Cross-project, space-containing, and shell-looking values all fail closed."""
    for build_service_account in (
        "build-sa@another-project.iam.gserviceaccount.com",
        "build sa@ci-placeholder-project.iam.gserviceaccount.com",
        "build-sa;echo leaked@ci-placeholder-project.iam.gserviceaccount.com",
    ):
        proc = subprocess.run(
            [
                "scripts/deploy_cloud_run.sh",
                "--env-file",
                "configs/cloud-run/ci.env",
                "--project-id",
                "ci-placeholder-project",
                "--region",
                "asia-northeast1",
                "--build-service-account",
                build_service_account,
            ],
            check=False,
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "PYTHONDONTWRITEBYTECODE": "1",
                "DISABLE_SESSION_AUTH": "false",
                "SKIP_FIRESTORE_INDEX_SYNC": "true",
            },
        )

        assert proc.returncode != 0
        assert "--build-service-account must be a service-account email in PROJECT_ID's project" in proc.stderr


def test_cloud_build_does_not_call_github_checks_api() -> None:
    """
    Contract: production deploy visibility is owned by GitHub Actions. Cloud
    Build must not call the GitHub Checks API from inside the remote build,
    because that network side-effect can block the backend image build and
    prevent Cloud Run deployment from starting.
    """

    config_text = Path("cloudbuild.backend.yaml").read_text(encoding="utf-8")
    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")

    forbidden = [
        "GITHUB_CHECKS_TOKEN",
        "_GITHUB_CHECKS_TOKEN",
        "_GITHUB_REPOSITORY",
        "_GITHUB_SHA",
        "_GITHUB_RUN_URL",
        "api.github.com/repos",
        "check-runs",
        "create-github-check",
        "complete-github-check",
    ]
    assert not [snippet for snippet in forbidden if snippet in config_text]
    assert not [snippet for snippet in forbidden if snippet in deploy_script]
