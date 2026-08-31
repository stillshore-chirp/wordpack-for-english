from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import yaml

def test_cloud_build_has_backend_config_and_deploy_script_uses_it() -> None:
    """
    Contract: Cloud Build must not rely on a repo-root Dockerfile being present in the remote workspace.
    We keep a dedicated Cloud Build config that explicitly uses Dockerfile.backend. The production
    workflow owns the single build; the deploy helper only accepts its immutable digest.
    """

    config_path = Path("cloudbuild.backend.yaml")
    assert config_path.exists(), "cloudbuild.backend.yaml must exist for Cloud Build backend image"

    config_text = config_path.read_text(encoding="utf-8")
    assert "Dockerfile.backend" in config_text, "cloudbuild.backend.yaml must reference Dockerfile.backend"
    assert "_IMAGE_URI" in config_text, "cloudbuild.backend.yaml must accept _IMAGE_URI substitution"

    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "--image-uri" in deploy_script
    assert "gcloud builds submit" not in deploy_script


def test_cloud_build_uses_explicit_dedicated_service_account_and_cloud_logging() -> None:
    """The build config keeps its explicit builder and log sink contract."""
    config_path = Path("cloudbuild.backend.yaml")
    config_text = config_path.read_text(encoding="utf-8")
    config = yaml.safe_load(config_text)

    assert isinstance(config, dict)
    assert config["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    assert config["options"]["requestedVerifyOption"] == "VERIFIED"
    assert "options:" in config_text
    assert "logging: CLOUD_LOGGING_ONLY" in config_text

    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    assert "scripts/build_backend_artifact.sh" in workflow
    assert "--build-service-account" in workflow
    assert "CLOUD_LOGGING_ONLY" in workflow

    build_helper = Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")
    assert "gcloud builds submit" in build_helper
    assert "--service-account" in build_helper
    assert "serviceAccounts/${BUILD_SERVICE_ACCOUNT}" in build_helper
    assert "git archive" in build_helper
    assert "mktemp -d" in build_helper
    assert build_helper.count('gcloud builds submit "${BUILD_CONTEXT}"') == 1
    assert "--show-provenance" in build_helper
    assert "sha256sum" in build_helper
    assert "native_provenance_snapshot_sha256=" in build_helper
    assert "build_id=" not in build_helper

    deploy_script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")
    assert "gcloud builds submit" not in deploy_script

    deployment_docs = Path("docs/deployment.md").read_text(encoding="utf-8")
    deploy_roles_start = deployment_docs.index("production deploy service account に必要な代表ロール:")
    build_roles_start = deployment_docs.index("dedicated Cloud Build service account に必要な代表ロール:")
    deploy_roles = deployment_docs[deploy_roles_start:build_roles_start]
    build_roles_end = deployment_docs.index("authenticated preflight service account は次の read-only role に限定します。", build_roles_start)
    build_roles = deployment_docs[build_roles_start:build_roles_end]
    assert "delivery provenance" in deployment_docs
    assert "https://spdx.dev/Document/v2.3" in deployment_docs
    assert "Cloud Build native provenance" in deployment_docs
    assert "gcloud builds submit ." not in deployment_docs
    assert "scripts/build_backend_artifact.sh" in deployment_docs
    assert "git archive TARGET_SHA" in deployment_docs
    assert '--source-digest "${SOURCE_DIGEST}"' in deployment_docs
    assert '--signer-digest "${SIGNER_DIGEST}"' in deployment_docs
    assert "github.sha" in deployment_docs
    assert "github.workflow_sha" in deployment_docs
    assert "--show-provenance" in deployment_docs
    assert "nativeProvenanceSnapshotSha256" in deployment_docs
    assert "roles/containeranalysis.occurrences.viewer" in deployment_docs
    assert "containeranalysis.googleapis.com" in deployment_docs
    assert "roles/artifactregistry.reader" in deploy_roles
    assert "roles/artifactregistry.writer" not in deploy_roles
    assert "roles/serviceusage.serviceUsageConsumer" in deploy_roles
    assert "roles/serviceusage.serviceUsageViewer" not in deploy_roles
    assert "roles/serviceusage.serviceUsageAdmin" not in deploy_roles
    assert "serviceusage.services.use" in deploy_roles
    assert "roles/artifactregistry.writer" in build_roles

    for doc_path in (
        "docs/deployment.md",
        "docs/infrastructure.md",
        "OPERATIONS.md",
        "docs/security/repository-hardening.md",
    ):
        doc_text = Path(doc_path).read_text(encoding="utf-8")
        assert "git archive TARGET_SHA" in doc_text
        assert "--source-digest" in doc_text
        assert "--signer-digest" in doc_text
        assert "github.sha" in doc_text
        assert "github.workflow_sha" in doc_text
        assert "Cloud Build native provenance" in doc_text
        assert "nativeProvenanceSnapshotSha256" in doc_text
        assert "nativeProvenanceDigest" not in doc_text
        assert "native_provenance_digest" not in doc_text
        assert "Syft 1.51.1" in doc_text
        assert "job-wide" in doc_text
        assert "retention" in doc_text
        assert "sunset" in doc_text
        for job_name in (
            "prepare-release-artifacts",
            "build-backend-artifact",
            "attest-backend-artifact",
            "deploy",
        ):
            assert job_name in doc_text
        assert "containeranalysis.googleapis.com" in doc_text
        assert "roles/containeranalysis.occurrences.viewer" in doc_text
        assert "gcloud builds submit ." not in doc_text


def test_deploy_script_requires_a_digest_bound_image_and_never_builds() -> None:
    """Cloud Build is owned by the workflow; the deploy helper consumes only a digest."""
    script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")

    assert "--image-uri <uri>" in script
    assert "sha256:" in script
    assert "gcloud builds submit" not in script
    assert "IMAGE_URI" in script
    assert "@sha256:" in script


def test_cloud_build_workflow_records_and_checks_registry_digest() -> None:
    """The workflow must compare the build result with the registry before promotion."""
    workflow = Path(".github/workflows/deploy-production.yml").read_text(encoding="utf-8")
    _assertions = (
        "scripts/build_backend_artifact.sh",
        "gcloud builds submit",
        "build-result",
        "image_summary.digest",
        "registry",
        "digest",
        "mismatch",
    )
    combined = workflow + "\n" + Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")
    missing = [needle for needle in _assertions if needle.lower() not in combined.lower()]
    assert not missing, f"Missing build/digest consistency checks: {missing}"


def test_backend_artifact_helper_is_explicit_and_secret_free() -> None:
    helper = Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")

    for marker in (
        "gcloud builds submit",
        "gcloud builds describe",
        "results.images[0].digest",
        "gcloud artifacts docker images describe",
        "--show-provenance",
        "provenance_summary",
        "inTotoSlsaProvenanceV1",
        "image_summary.digest",
        "Cloud Build result digest and registry digest mismatch",
        "docker pull",
        "docker run",
        "GITHUB_OUTPUT",
    ):
        assert marker in helper
    assert "GCP_SA_KEY" not in helper
    assert "credentials_json" not in helper
    assert "CLOUD_RUN_ENV_FILE_BASE64" not in helper
    assert "--format='value(id)'" in helper
    assert "@${REGISTRY_DIGEST}" in helper

    ci_workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "shellcheck" in ci_workflow
    assert "scripts/build_backend_artifact.sh" in ci_workflow
    assert "scripts/verify_backend_artifact_attestations.sh" in ci_workflow


def _run_backend_artifact_helper(
    tmp_path: Path,
    registry_digest: str,
    *,
    native_provenance_missing: bool = False,
    native_builder: str | None = None,
    native_source_repository: str | None = None,
    native_build_source_repository: str | None = None,
    native_build_source_path: str | None = None,
    native_target_sha: str | None = None,
    native_digest: str | None = None,
    native_build_id: str | None = None,
    native_omit_scm_metadata: bool = False,
    native_missing_build_config: bool = False,
    dirty_tree: bool = False,
    dirty_tree_kind: str = "tracked",
    inject_archive_hazards: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gcloud_log = tmp_path / "gcloud.log"
    docker_log = tmp_path / "docker.log"
    output_path = tmp_path / "github-output"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [[ \"${1:-}\" == builds && \"${2:-}\" == submit ]]; then\n"
        "  context=\"${3:-}\"\n"
        "  [[ -d \"${context}\" ]] || { echo 'missing build context' >&2; exit 2; }\n"
        "  rm -rf -- \"${CAPTURED_CONTEXT}\"\n"
        "  cp -a -- \"${context}\" \"${CAPTURED_CONTEXT}\"\n"
        "  printf 'build-contract-1\\n'\n"
        "elif [[ \"${1:-}\" == builds && \"${2:-}\" == describe ]]; then\n"
        "  if [[ \"$*\" == *'results.images[0].digest'* ]]; then printf '%s\\n' \"${BUILD_DIGEST}\"; else printf 'SUCCESS\\n'; fi\n"
        "elif [[ \"${1:-}\" == artifacts && \"${2:-}\" == docker && \"${3:-}\" == images && \"${4:-}\" == describe ]]; then\n"
        "  if [[ \"$*\" == *'--show-provenance'* ]]; then\n"
        "    cat \"${NATIVE_PROVENANCE}\"\n"
        "  else\n"
        "    printf '%s\\n' \"${REGISTRY_DIGEST}\"\n"
        "  fi\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${DOCKER_LOG}\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_curl.chmod(0o755)
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "if [[ \"${FAKE_GIT_DIRTY:-false}\" == true && \"${FAKE_GIT_DIRTY_KIND:-tracked}\" == tracked && \"${1:-}\" == diff && \"$*\" != *--cached* ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"${FAKE_GIT_DIRTY:-false}\" == true && \"${FAKE_GIT_DIRTY_KIND:-tracked}\" == index && \"${1:-}\" == diff && \"$*\" == *--cached* ]]; then\n"
        "  exit 1\n"
        "fi\n"
        "if [[ \"${FAKE_GIT_DIRTY:-false}\" == true && \"${FAKE_GIT_DIRTY_KIND:-tracked}\" == untracked && \"${1:-}\" == ls-files ]]; then\n"
        "  printf 'synthetic-build-input\\n'\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${1:-}\" == diff || \"${1:-}\" == ls-files || \"${1:-}\" == status ]]; then\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${INJECT_ARCHIVE_HAZARDS:-false}\" == true && \"${1:-}\" == archive ]]; then\n"
        "  archive_output=''\n"
        "  for argument in \"$@\"; do\n"
        "    case \"${argument}\" in --output=*) archive_output=\"${argument#--output=}\" ;; esac\n"
        "  done\n"
        "  [[ -n \"${archive_output}\" ]] || exit 3\n"
        f'  "{real_git}" "$@"\n'
        "  injection_root=\"$(mktemp -d)\"\n"
        "  mkdir -p \"${injection_root}/apps/backend/backend/PRIVATE\"\n"
        "  ln -s 'missing-malformed-target' \"${injection_root}/apps/backend/backend/malformed_link.py\"\n"
        "  printf 'synthetic fixture only\\n' > \"${injection_root}/apps/backend/backend/PRIVATE/SECRET_contract.py\"\n"
        "  tar --append --file=\"${archive_output}\" --directory=\"${injection_root}\" -- \\\n"
        "    apps/backend/backend/malformed_link.py \\\n"
        "    apps/backend/backend/PRIVATE/SECRET_contract.py\n"
        "  rm -rf -- \"${injection_root}\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ \"${INJECT_ARCHIVE_HAZARDS:-false}\" == true && \"${1:-}\" == ls-tree ]]; then\n"
        f'  "{real_git}" "$@"\n'
        "  printf '120000\\tapps/backend/backend/malformed_link.py\\0'\n"
        "  printf '100644\\tapps/backend/backend/PRIVATE/SECRET_contract.py\\0'\n"
        "  exit 0\n"
        "fi\n"
        f'exec "{real_git}" "$@"\n',
        encoding="utf-8",
    )
    fake_git.chmod(0o755)

    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    build_digest = "sha256:" + "a" * 64
    builder_workflow = (
        "https://github.com/stillshore-chirp/wordpack-for-english/"
        ".github/workflows/deploy-production.yml@refs/heads/main"
    )
    native_digest = native_digest or build_digest
    native_provenance_path = tmp_path / "native-provenance.json"
    if not native_provenance_missing:
        native_provenance_path.write_text(
            json.dumps(
                {
                    "image_summary": {
                        "digest": native_digest,
                        "fully_qualified_digest": (
                            "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@"
                            f"{native_digest}"
                        ),
                    },
                    "provenance_summary": {
                        "provenance": [
                            {
                                "build": {
                                    "inTotoSlsaProvenanceV1": {
                                        "predicateType": "https://slsa.dev/provenance/v1",
                                        "subject": [
                                            {
                                                "name": "https://asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend",
                                                "digest": {
                                                    "sha256": native_digest.removeprefix("sha256:")
                                                },
                                            }
                                        ],
                                        "predicate": {
                                            "buildDefinition": {
                                                "buildType": "https://cloud.google.com/build/gcb-buildtypes/google-worker/v1",
                                                "externalParameters": {
                                                    "buildConfigSource": None
                                                    if native_omit_scm_metadata
                                                    else {
                                                        "repository": native_build_source_repository
                                                        or "git+https://github.com/stillshore-chirp/wordpack-for-english",
                                                        "ref": "refs/heads/main",
                                                        "path": native_build_source_path
                                                        or "cloudbuild.backend.yaml",
                                                    },
                                                    "buildConfig": (
                                                        None
                                                        if not native_omit_scm_metadata
                                                        else (
                                                            None
                                                            if native_missing_build_config
                                                            else "eyJzdGVwcyI6W119"
                                                        )
                                                    ),
                                                    "substitutions": {
                                                        "_SOURCE_REPOSITORY": native_source_repository
                                                        or "https://github.com/stillshore-chirp/wordpack-for-english",
                                                        "_TARGET_SHA": native_target_sha or target_sha,
                                                        "_BUILDER_WORKFLOW": builder_workflow,
                                                    }
                                                },
                                                "resolvedDependencies": []
                                                if native_omit_scm_metadata
                                                else [
                                                    {
                                                        "digest": {"gitCommit": native_target_sha or target_sha},
                                                        "uri": (
                                                            "git+https://github.com/stillshore-chirp/wordpack-for-english"
                                                            "@refs/heads/main"
                                                        ),
                                                    }
                                                ],
                                            },
                                            "runDetails": {
                                                "builder": {
                                                    "id": native_builder
                                                    or "https://cloudbuild.googleapis.com/GoogleHostedWorker"
                                                },
                                                "metadata": {
                                                    "invocationId": (
                                                        "https://cloudbuild.googleapis.com/v1/projects/"
                                                        "ci-placeholder-project/locations/asia-northeast1/builds/"
                                                        f"{native_build_id or 'build-contract-1'}"
                                                    )
                                                },
                                            },
                                        },
                                    }
                                }
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
    proc = subprocess.run(
        [
            "bash",
            "scripts/build_backend_artifact.sh",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--repository",
            "stillshore-chirp/wordpack-for-english",
            "--target-sha",
            target_sha,
            "--builder-workflow",
            "https://github.com/stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main",
            "--build-service-account",
            "build-sa@ci-placeholder-project.iam.gserviceaccount.com",
        ],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "BUILD_DIGEST": build_digest,
            "REGISTRY_DIGEST": registry_digest,
            "GCLOUD_LOG": str(gcloud_log),
            "DOCKER_LOG": str(docker_log),
            "CAPTURED_CONTEXT": str(tmp_path / "captured-context"),
            "GITHUB_OUTPUT": str(output_path),
            "NATIVE_PROVENANCE": str(native_provenance_path),
            "FAKE_GIT_DIRTY": "true" if dirty_tree else "false",
            "FAKE_GIT_DIRTY_KIND": dirty_tree_kind,
            "INJECT_ARCHIVE_HAZARDS": "true" if inject_archive_hazards else "false",
        },
    )
    return proc, docker_log


def test_backend_artifact_helper_rejects_build_registry_digest_mismatch(tmp_path: Path) -> None:
    proc, docker_log = _run_backend_artifact_helper(tmp_path, "sha256:" + "b" * 64)

    assert proc.returncode != 0
    assert "digest mismatch" in (proc.stdout + proc.stderr).lower()
    assert "pull" not in docker_log.read_text(encoding="utf-8")
    assert "run" not in docker_log.read_text(encoding="utf-8")


def test_backend_artifact_helper_archives_target_commit_and_excludes_dirty_inputs(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    helper = Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")
    assert "git archive" in helper
    assert "mktemp -d" in helper
    assert 'gcloud builds submit "${BUILD_CONTEXT}"' in helper
    assert '--ignore-file="${BUILD_IGNORE_FILE}"' in helper
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
    assert "configs/cloud-run/*.env" in dockerignore
    for allowlist_entry in (
        "**",
        "!Dockerfile.backend",
        "!cloudbuild.backend.yaml",
        "!requirements.txt",
        "!apps/",
        "!apps/backend/",
        "!apps/backend/backend/",
        "!apps/backend/backend/**/",
        "!apps/backend/backend/*.py",
        "!apps/backend/backend/**/*.py",
        "apps/backend/backend/**/*credential*.py",
        "apps/backend/backend/**/*secret*.py",
        "apps/backend/backend/**/*token*.py",
    ):
        assert allowlist_entry in helper
    assert "!apps/**" not in helper

    for kind in ("tracked", "index", "untracked"):
        generated_env = Path(f".env.build-contract-{tmp_path.name}-{kind}")
        generated_env.write_text("SESSION_SECRET_KEY=must-not-be-uploaded\n", encoding="utf-8")
        proc, docker_log = _run_backend_artifact_helper(
            tmp_path / kind,
            digest,
            dirty_tree=True,
            dirty_tree_kind=kind,
        )
        generated_env.unlink(missing_ok=True)

        assert proc.returncode == 0, proc.stdout + proc.stderr
        captured_context = tmp_path / kind / "captured-context"
        assert (captured_context / "cloudbuild.backend.yaml").is_file()
        assert (captured_context / "Dockerfile.backend").is_file()
        assert (captured_context / "requirements.txt").is_file()
        assert (captured_context / ".gcloudignore").is_file()
        generated_ignore = (captured_context / ".gcloudignore").read_text(encoding="utf-8")
        assert ".env" not in generated_ignore
        assert generated_ignore.splitlines()[1:] == [
            "**",
            "!.gcloudignore",
            "!.dockerignore",
            "!Dockerfile.backend",
            "!cloudbuild.backend.yaml",
            "!requirements.txt",
            "!apps/",
            "!apps/backend/",
            "!apps/backend/backend/",
            "!apps/backend/backend/**/",
            "!apps/backend/backend/*.py",
            "!apps/backend/backend/**/*.py",
            "apps/backend/backend/**/*credential*.py",
            "apps/backend/backend/**/*secret*.py",
            "apps/backend/backend/**/*token*.py",
        ]
        assert not (captured_context / generated_env.name).exists()
        submit_line = next(
            line
            for line in (tmp_path / kind / "gcloud.log").read_text(encoding="utf-8").splitlines()
            if line.startswith("builds submit ")
        )
        assert not submit_line.startswith("builds submit . ")
        assert str(captured_context) not in submit_line
        assert "--ignore-file=" in submit_line
        assert "pull" in docker_log.read_text(encoding="utf-8")


def test_backend_artifact_helper_materializes_exact_physical_allowlist(tmp_path: Path) -> None:
    """Excluded malformed symlinks and tracked secret-like files never reach gcloud."""
    digest = "sha256:" + "a" * 64
    helper = Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")
    for secret_marker in ("credential", "secret", "token"):
        assert (
            f":(exclude,icase,glob)apps/backend/backend/**/*{secret_marker}*.py"
            in helper
        )
    proc, _ = _run_backend_artifact_helper(
        tmp_path,
        digest,
        inject_archive_hazards=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    captured_context = tmp_path / "captured-context"
    assert not (captured_context / "Dockerfile").exists()
    assert not (captured_context / "Dockerfile").is_symlink()
    assert not any(path.is_symlink() for path in captured_context.rglob("*"))
    assert not (captured_context / "apps/backend/backend/malformed_link.py").exists()
    assert not (captured_context / "apps/backend/backend/PRIVATE/SECRET_contract.py").exists()

    target_entries = subprocess.check_output(
        ["git", "ls-tree", "-r", "--format=%(objectmode)\t%(path)", "HEAD", "--", "apps/backend/backend"],
        text=True,
    ).splitlines()
    expected_files = {
        ".dockerignore",
        "Dockerfile.backend",
        "cloudbuild.backend.yaml",
        "requirements.txt",
        ".gcloudignore",
        *{
            path.split("\t", 1)[1]
            for path in target_entries
            if path.startswith(("100644\t", "100755\t"))
            if path.endswith(".py")
            and not re.search(r"(credential|secret|token)", path, re.IGNORECASE)
        },
    }
    actual_files = {
        path.relative_to(captured_context).as_posix()
        for path in captured_context.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files


def test_cloud_build_upload_allowlist_rejects_nested_secret_like_paths(tmp_path: Path) -> None:
    helper = Path("scripts/build_backend_artifact.sh").read_text(encoding="utf-8")
    policy_match = re.search(r"<<'GCLOUDIGNORE'\n(?P<policy>.*?)\nGCLOUDIGNORE", helper, re.DOTALL)
    assert policy_match is not None
    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    (policy_root / ".gitignore").write_text(policy_match.group("policy") + "\n", encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(policy_root)], check=True)

    allowed = (
        "Dockerfile.backend",
        "cloudbuild.backend.yaml",
        "requirements.txt",
        "apps/backend/backend/main.py",
        "apps/backend/backend/domain/wordpack/records.py",
    )
    excluded = (
        ".env.ci",
        "configs/cloud-run/ci.env",
        "apps/frontend/src/main.tsx",
        "apps/backend/backend/private/.env.production",
        "apps/backend/backend/private/credential.json",
        "apps/backend/backend/private/secret.py",
        "apps/backend/backend/private/token.py",
    )
    for relative_path in (*allowed, *excluded):
        candidate = policy_root / relative_path
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.touch()

    for relative_path in allowed:
        result = subprocess.run(
            ["git", "-C", str(policy_root), "check-ignore", "--no-index", relative_path],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, relative_path
    for relative_path in excluded:
        result = subprocess.run(
            ["git", "-C", str(policy_root), "check-ignore", "--no-index", relative_path],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, relative_path


def test_backend_artifact_helper_smokes_the_same_digest_and_writes_only_immutable_uri(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    proc, docker_log = _run_backend_artifact_helper(tmp_path, digest)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    docker_calls = docker_log.read_text(encoding="utf-8")
    assert f"pull --quiet asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@{digest}" in docker_calls
    assert f"wordpack/backend@{digest}" in docker_calls
    gcloud_calls = (tmp_path / "gcloud.log").read_text(encoding="utf-8")
    assert f"wordpack/backend@{digest}" in gcloud_calls
    assert "--show-provenance" in gcloud_calls
    output = (tmp_path / "github-output").read_text(encoding="utf-8")
    assert f"image_digest={digest}" in output
    assert f"image_uri=asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend@{digest}" in output
    assert re.search(r"native_provenance_snapshot_sha256=sha256:[0-9a-f]{64}", output)
    assert "native_provenance_digest=" not in output
    assert "build_id=" not in output
    assert "native_provenance_build_id=" not in output
    assert "build-contract-1" not in proc.stdout + proc.stderr
    assert digest not in proc.stdout + proc.stderr


def test_backend_artifact_helper_rejects_invalid_native_provenance(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    cases = (
        {"native_provenance_missing": True},
        {"native_builder": "https://example.invalid/builder"},
        {"native_source_repository": "https://github.com/other/repository"},
        {"native_build_source_repository": "git+https://github.com/other/repository"},
        {"native_build_source_path": "other-cloudbuild.yaml"},
        {"native_target_sha": "b" * 40},
        {"native_digest": "sha256:" + "b" * 64},
        {"native_build_id": "different-build"},
        {
            "native_omit_scm_metadata": True,
            "native_missing_build_config": True,
        },
    )
    for index, overrides in enumerate(cases):
        proc, docker_log = _run_backend_artifact_helper(
            tmp_path / str(index),
            digest,
            **overrides,
        )
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert "pull" not in docker_log.read_text(encoding="utf-8")


def test_backend_artifact_helper_accepts_local_archive_provenance_without_scm_metadata(
    tmp_path: Path,
) -> None:
    digest = "sha256:" + "a" * 64
    proc, docker_log = _run_backend_artifact_helper(
        tmp_path,
        digest,
        native_omit_scm_metadata=True,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "pull" in docker_log.read_text(encoding="utf-8")


def test_backend_artifact_helper_accepts_official_dot_git_source_uri(tmp_path: Path) -> None:
    digest = "sha256:" + "a" * 64
    proc, docker_log = _run_backend_artifact_helper(
        tmp_path,
        digest,
        native_build_source_repository=(
            "git+https://github.com/stillshore-chirp/wordpack-for-english.git"
        ),
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "pull" in docker_log.read_text(encoding="utf-8")


def _run_attestation_verifier(
    tmp_path: Path,
    *,
    target_sha: str,
    source_digest: str | None = None,
    signer_digest: str | None = None,
    runtime_signer_digest: str | None = None,
    image_digest: str,
    attested_target_sha: str | None = None,
    attested_workflow: str | None = None,
    attested_builder: str | None = None,
    attested_underlying_builder: str | None = None,
    attested_cloud_build_provenance: str | None = None,
    attested_native_provenance_snapshot_sha256: str | None = None,
    expected_native_provenance_snapshot_sha256: str | None = None,
    local_source_repository: str | None = None,
    attested_source_repository: str | None = None,
    attested_digest: str | None = None,
    missing_sbom: bool = False,
) -> subprocess.CompletedProcess[str]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = "stillshore-chirp/wordpack-for-english"
    workflow = (
        "https://github.com/stillshore-chirp/wordpack-for-english/"
        ".github/workflows/deploy-production.yml@refs/heads/main"
    )
    build_type = f"{workflow}#backend-cloud-build-v1"
    image_name = "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend"
    native_provenance_snapshot_sha256 = "sha256:" + "c" * 64
    expected_native_provenance_snapshot_sha256 = (
        expected_native_provenance_snapshot_sha256 or native_provenance_snapshot_sha256
    )
    digest_hex = image_digest.removeprefix("sha256:")
    attested_target_sha = attested_target_sha or target_sha
    attested_workflow = attested_workflow or workflow
    attested_builder = attested_builder or attested_workflow
    attested_underlying_builder = (
        attested_underlying_builder or "https://cloudbuild.googleapis.com/GoogleHostedWorker"
    )
    attested_cloud_build_provenance = attested_cloud_build_provenance or "required"
    attested_native_provenance_snapshot_sha256 = (
        attested_native_provenance_snapshot_sha256 or native_provenance_snapshot_sha256
    )
    local_source_repository = local_source_repository or f"https://github.com/{repository}"
    attested_source_repository = attested_source_repository or f"https://github.com/{repository}"
    attested_digest = (attested_digest or image_digest).removeprefix("sha256:")
    source_digest = source_digest or target_sha
    signer_digest = signer_digest or "d" * 40
    runtime_signer_digest = runtime_signer_digest or signer_digest

    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(
        json.dumps(
            {
                "buildDefinition": {
                    "buildType": build_type,
                    "externalParameters": {
                        "sourceRepository": local_source_repository,
                        "targetSha": target_sha,
                        "builderWorkflow": workflow,
                        "underlyingBuilder": "https://cloudbuild.googleapis.com/GoogleHostedWorker",
                        "cloudBuildProvenance": "required",
                        "nativeProvenanceSnapshotSha256": native_provenance_snapshot_sha256,
                    },
                    "resolvedDependencies": [
                        {
                            "uri": local_source_repository,
                            "digest": {"gitCommit": target_sha},
                        }
                    ],
                },
                "runDetails": {
                    "builder": {"id": workflow}
                },
            }
        ),
        encoding="utf-8",
    )
    sbom_path = tmp_path / "sbom.json"
    if not missing_sbom:
        sbom_path.write_text(
            json.dumps({"spdxVersion": "SPDX-2.3", "name": "backend-image"}),
            encoding="utf-8",
        )

    provenance_attestation = tmp_path / "provenance-attestation.json"
    provenance_attestation.write_text(
        json.dumps(
            [
                {
                    "verificationResult": {
                        "statement": {
                            "predicateType": "https://slsa.dev/provenance/v1",
                            "subject": [{"name": image_name, "digest": {"sha256": attested_digest}}],
                            "predicate": {
                                "buildDefinition": {
                                    "buildType": build_type,
                                    "externalParameters": {
                                        "sourceRepository": attested_source_repository,
                                        "targetSha": attested_target_sha,
                                        "builderWorkflow": attested_workflow,
                                        "underlyingBuilder": attested_underlying_builder,
                                        "cloudBuildProvenance": attested_cloud_build_provenance,
                                        "nativeProvenanceSnapshotSha256": attested_native_provenance_snapshot_sha256,
                                    },
                                    "resolvedDependencies": [
                                        {
                                            "uri": attested_source_repository,
                                            "digest": {"gitCommit": attested_target_sha},
                                        }
                                    ],
                                },
                                "runDetails": {
                                    "builder": {"id": attested_builder}
                                },
                            },
                        }
                    }
                }
            ]
        ),
        encoding="utf-8",
    )
    sbom_attestation = tmp_path / "sbom-attestation.json"
    sbom_attestation.write_text(
        json.dumps(
            [
                {
                    "verificationResult": {
                        "statement": {
                            "predicateType": "https://spdx.dev/Document/v2.3",
                            "subject": [{"name": image_name, "digest": {"sha256": attested_digest}}],
                            "predicate": {"spdxVersion": "SPDX-2.3"},
                        }
                    }
                }
            ]
        ),
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    fake_gh.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${GH_LOG}\"\n"
        "if [[ \"$*\" == *'https://slsa.dev/provenance/v1'* ]]; then\n"
        "  cat \"${PROVENANCE_ATTESTATION}\"\n"
        "else\n"
        "  cat \"${SBOM_ATTESTATION}\"\n"
        "fi\n",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    gh_log = tmp_path / "gh.log"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "GH_TOKEN": "synthetic-token",
        "GITHUB_SHA": source_digest,
        "GITHUB_WORKFLOW_SHA": runtime_signer_digest,
        "GH_LOG": str(gh_log),
        "PROVENANCE_ATTESTATION": str(provenance_attestation),
        "SBOM_ATTESTATION": str(sbom_attestation),
    }
    return subprocess.run(
        [
            "scripts/verify_backend_artifact_attestations.sh",
            "--image-uri",
            f"{image_name}@{image_digest}",
            "--repository",
            repository,
            "--target-sha",
            target_sha,
            "--source-digest",
            source_digest,
            "--signer-digest",
            signer_digest,
            "--native-provenance-snapshot-sha256",
            expected_native_provenance_snapshot_sha256,
            "--builder-workflow",
            workflow,
            "--provenance",
            str(provenance_path),
            "--sbom",
            str(sbom_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_attestation_verifier_accepts_matching_provenance_and_sbom(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    proc = _run_attestation_verifier(tmp_path, target_sha=target_sha, image_digest="sha256:" + "a" * 64)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = (tmp_path / "gh.log").read_text(encoding="utf-8")
    assert calls.count("attestation verify") == 2
    assert "--deny-self-hosted-runners" in calls


def test_attestation_verifier_separates_source_and_signer_digests_from_artifact_target(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source_digest = "c" * 40
    signer_digest = "d" * 40
    proc = _run_attestation_verifier(
        tmp_path,
        target_sha=target_sha,
        source_digest=source_digest,
        signer_digest=signer_digest,
        image_digest="sha256:" + "a" * 64,
    )

    assert proc.returncode == 0, proc.stdout + proc.stderr
    calls = (tmp_path / "gh.log").read_text(encoding="utf-8")
    assert f"--source-digest {source_digest}" in calls
    assert f"--signer-digest {signer_digest}" in calls


def test_attestation_verifier_rejects_wrong_runtime_signer_digest(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    proc = _run_attestation_verifier(
        tmp_path,
        target_sha=target_sha,
        signer_digest="d" * 40,
        runtime_signer_digest="e" * 40,
        image_digest="sha256:" + "a" * 64,
    )

    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_attestation_verifier_keeps_github_builder_separate_from_cloud_build(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    proc = _run_attestation_verifier(
        tmp_path,
        target_sha=target_sha,
        image_digest="sha256:" + "a" * 64,
        attested_builder="https://cloudbuild.googleapis.com/GoogleHostedWorker",
    )

    assert proc.returncode != 0, proc.stdout + proc.stderr


def test_attestation_verifier_requires_cloud_build_binding_parameters(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    cases = (
        {"attested_underlying_builder": "https://example.invalid/builder"},
        {"attested_cloud_build_provenance": "optional"},
        {"attested_native_provenance_snapshot_sha256": "sha256:" + "e" * 64},
        {"expected_native_provenance_snapshot_sha256": "sha256:" + "e" * 64},
        {"local_source_repository": "https://github.com/other/repository"},
        {"attested_source_repository": "https://github.com/other/repository"},
    )
    for index, overrides in enumerate(cases):
        proc = _run_attestation_verifier(
            tmp_path / str(index),
            target_sha=target_sha,
            image_digest="sha256:" + "a" * 64,
            **overrides,
        )
        assert proc.returncode != 0, proc.stdout + proc.stderr


def test_attestation_verifier_rejects_wrong_target_workflow_digest_or_missing_sbom(tmp_path: Path) -> None:
    target_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    wrong_sha = "b" * 40
    wrong_workflow = "https://github.com/other/repository/.github/workflows/deploy.yml@refs/heads/main"
    wrong_digest = "sha256:" + "b" * 64

    cases = (
        {"attested_target_sha": wrong_sha},
        {"attested_workflow": wrong_workflow},
        {"attested_digest": wrong_digest},
        {"missing_sbom": True},
    )
    for index, overrides in enumerate(cases):
        proc = _run_attestation_verifier(
            tmp_path / str(index),
            target_sha=target_sha,
            image_digest="sha256:" + "a" * 64,
            **overrides,
        )
        assert proc.returncode != 0, proc.stdout + proc.stderr


def test_cleanup_temp_files_handles_env_file_and_preserves_failure_status(tmp_path: Path) -> None:
    """The EXIT cleanup must remove generated env material without masking failures."""
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

    ENV_VARS_FILE=""
    cleanup_temp_files

    ENV_VARS_FILE="{tmp_path}/env.yaml"
    touch "$ENV_VARS_FILE"
    cleanup_temp_files
    [[ ! -e "$ENV_VARS_FILE" ]]

    ENV_VARS_FILE="{tmp_path}/env-both.yaml"
    touch "$ENV_VARS_FILE"
    cleanup_temp_files
    [[ ! -e "$ENV_VARS_FILE" ]]

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


def test_deploy_script_rejects_tagged_or_cross_project_images_before_gcloud() -> None:
    """Tag and wrong-project references fail closed before any deploy command."""
    script = Path("scripts/deploy_cloud_run.sh").read_text(encoding="utf-8")

    assert "image uri" in script.lower() or "image-uri" in script.lower()
    assert "sha256" in script
    assert "PROJECT_ID" in script
    assert "ARTIFACT_REPOSITORY" in script
    assert "exit 1" in script


def _run_digest_deploy(tmp_path: Path, image_uri: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    gcloud_log = tmp_path / "gcloud.log"
    fake_gcloud = fake_bin / "gcloud"
    fake_gcloud.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "printf '%s\\n' \"$*\" >> \"${GCLOUD_LOG}\"\n"
        "if [[ \"${1:-}\" == builds && \"${2:-}\" == submit ]]; then\n"
        "  touch \"${BUILD_MARKER}\"\n"
        "  exit 99\n"
        "fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_gcloud.chmod(0o755)
    build_marker = tmp_path / "build-submitted"
    proc = subprocess.run(
        [
            "scripts/deploy_cloud_run.sh",
            "--env-file",
            "configs/cloud-run/ci.env",
            "--project-id",
            "ci-placeholder-project",
            "--region",
            "asia-northeast1",
            "--service",
            "wordpack-backend",
            "--image-uri",
            image_uri,
            "--no-traffic",
            "--traffic-tag",
            "candidate",
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
            "GCLOUD_LOG": str(gcloud_log),
            "BUILD_MARKER": str(build_marker),
            "DEPLOYMENT_VERSION": "contract-test",
        },
    )
    return proc, build_marker


def test_digest_deploy_uses_supplied_image_without_cloud_build(tmp_path: Path) -> None:
    digest = "a" * 64
    image_uri = (
        "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend"
        f"@sha256:{digest}"
    )
    proc, build_marker = _run_digest_deploy(tmp_path, image_uri)

    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert not build_marker.exists()
    calls = (tmp_path / "gcloud.log").read_text(encoding="utf-8")
    assert "builds submit" not in calls
    assert f"@sha256:{digest}" in calls


def test_digest_deploy_rejects_tag_and_wrong_project_before_gcloud(tmp_path: Path) -> None:
    invalid_images = (
        "asia-northeast1-docker.pkg.dev/ci-placeholder-project/wordpack/backend:deadbeef",
        "asia-northeast1-docker.pkg.dev/another-project/wordpack/backend@sha256:" + "a" * 64,
        "asia-northeast1-docker.pkg.dev/ci-placeholder-project/other/backend@sha256:" + "a" * 64,
    )
    for index, image_uri in enumerate(invalid_images):
        proc, build_marker = _run_digest_deploy(tmp_path / str(index), image_uri)
        assert proc.returncode != 0, proc.stdout + proc.stderr
        assert not build_marker.exists()


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
