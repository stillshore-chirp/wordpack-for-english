#!/usr/bin/env bash
set -euo pipefail

# Build the backend once in Cloud Build and exercise the exact registry digest.
# Image metadata and the two verification values are written to GITHUB_OUTPUT;
# build responses and credential-bearing command output stay out of workflow logs.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"; }
err() { printf 'Error: %s\n' "$*" >&2; }
fail() { err "$*"; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }
require_value() { [[ $# -ge 2 && -n "$2" ]] || fail "$1 requires a non-empty value"; }

usage() {
  cat <<'USAGE'
Build the backend image once and verify its immutable registry digest.

Usage:
  scripts/build_backend_artifact.sh [options]

Options:
  --project-id <id>             Google Cloud project ID
  --region <region>             Artifact Registry region
  --artifact-repo <path>        Artifact Registry image path (default: wordpack/backend)
  --repository <owner/repo>     GitHub repository identity
  --target-sha <sha>            Checked-out 40-character commit SHA
  --builder-workflow <uri>      Exact production workflow identity
  --build-service-account <email>
                                Dedicated Cloud Build service-account email
  --machine-type <type>         Cloud Build machine type (default: e2-medium)
  --timeout <duration>          Cloud Build timeout (default: 30m)
  -h, --help                   Show this help
USAGE
}

PROJECT_ID=""
REGION=""
ARTIFACT_REPOSITORY="wordpack/backend"
REPOSITORY=""
TARGET_SHA=""
BUILDER_WORKFLOW=""
BUILD_SERVICE_ACCOUNT=""
MACHINE_TYPE="e2-medium"
BUILD_TIMEOUT="30m"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      require_value "$@"
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      require_value "$@"
      REGION="$2"
      shift 2
      ;;
    --artifact-repo)
      require_value "$@"
      ARTIFACT_REPOSITORY="$2"
      shift 2
      ;;
    --repository)
      require_value "$@"
      REPOSITORY="$2"
      shift 2
      ;;
    --target-sha)
      require_value "$@"
      TARGET_SHA="$2"
      shift 2
      ;;
    --builder-workflow)
      require_value "$@"
      BUILDER_WORKFLOW="$2"
      shift 2
      ;;
    --build-service-account)
      require_value "$@"
      BUILD_SERVICE_ACCOUNT="$2"
      shift 2
      ;;
    --machine-type)
      require_value "$@"
      MACHINE_TYPE="$2"
      shift 2
      ;;
    --timeout)
      require_value "$@"
      BUILD_TIMEOUT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

[[ "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || \
  fail "project ID is not a valid Google Cloud project ID"
[[ "$REGION" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || \
  fail "region is not a valid Artifact Registry location"
[[ "$ARTIFACT_REPOSITORY" =~ ^[a-z0-9][a-z0-9._-]*(/[a-z0-9][a-z0-9._-]*)*$ ]] || \
  fail "artifact repository image path is invalid"
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
  fail "repository must use the owner/repository form"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || \
  fail "target SHA must be a lowercase 40-character commit SHA"
[[ "$MACHINE_TYPE" =~ ^[A-Za-z0-9._-]+$ ]] || fail "machine type is invalid"
[[ "$BUILD_TIMEOUT" =~ ^[0-9]+[smhd]$ ]] || fail "Cloud Build timeout is invalid"

EXPECTED_BUILDER_WORKFLOW="https://github.com/${REPOSITORY}/.github/workflows/deploy-production.yml@refs/heads/main"
[[ "$BUILDER_WORKFLOW" == "$EXPECTED_BUILDER_WORKFLOW" ]] || \
  fail "builder workflow must be the pinned production workflow on main"
[[ "$BUILD_SERVICE_ACCOUNT" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]@${PROJECT_ID}\.iam\.gserviceaccount\.com$ ]] || \
  fail "build service account must belong to the target project and use a valid account ID"

require_cmd git
require_cmd gcloud
require_cmd docker
require_cmd curl
require_cmd jq
require_cmd sha256sum
require_cmd tar
[[ -n "${GITHUB_OUTPUT:-}" ]] || fail "GITHUB_OUTPUT is required"
[[ -f "${REPO_ROOT}/cloudbuild.backend.yaml" ]] || fail "cloudbuild.backend.yaml is missing"
[[ -f "${REPO_ROOT}/.env.ci" ]] || fail ".env.ci is required for the digest health smoke"

CHECKED_OUT_SHA="$(git rev-parse HEAD 2>/dev/null || true)"
[[ "$CHECKED_OUT_SHA" =~ ^[0-9a-f]{40}$ && "$CHECKED_OUT_SHA" == "$TARGET_SHA" ]] || \
  fail "checked-out HEAD does not match the requested target SHA"

IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}"
IMAGE_TAG_URI="${IMAGE_NAME}:${TARGET_SHA}"
SUBSTITUTIONS="_IMAGE_URI=${IMAGE_TAG_URI},_SOURCE_REPOSITORY=https://github.com/${REPOSITORY},_TARGET_SHA=${TARGET_SHA},_BUILDER_WORKFLOW=${BUILDER_WORKFLOW}"
BUILD_ID=""
SUBMIT_OUTPUT=""
NATIVE_PROVENANCE_OUTPUT=""
BUILD_CONTEXT_ROOT=""
BUILD_CONTEXT=""
CONTEXT_ARCHIVE=""
SMOKE_CONTAINER="wordpack-backend-digest-smoke-${BASHPID}"

cleanup() {
  local previous_status=$?
  if [[ -n "${SMOKE_CONTAINER:-}" ]]; then
    docker rm --force "${SMOKE_CONTAINER}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${SUBMIT_OUTPUT:-}" && -f "$SUBMIT_OUTPUT" ]]; then
    rm -f "$SUBMIT_OUTPUT" || true
  fi
  if [[ -n "${NATIVE_PROVENANCE_OUTPUT:-}" && -f "$NATIVE_PROVENANCE_OUTPUT" ]]; then
    rm -f "$NATIVE_PROVENANCE_OUTPUT" || true
  fi
  if [[ -n "${BUILD_CONTEXT_ROOT:-}" && -d "$BUILD_CONTEXT_ROOT" ]]; then
    rm -rf -- "$BUILD_CONTEXT_ROOT" || true
  fi
  return "$previous_status"
}
trap cleanup EXIT

# Build only the requested commit. The archive is intentionally made from the
# Git object database instead of the checkout, so staged, dirty, ignored, and
# untracked files (including generated env/secret material) cannot enter the
# remote build context.
BUILD_CONTEXT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wordpack-backend-build.XXXXXX")"
chmod 700 "$BUILD_CONTEXT_ROOT"
BUILD_CONTEXT="${BUILD_CONTEXT_ROOT}/context"
CONTEXT_ARCHIVE="${BUILD_CONTEXT_ROOT}/context.tar"
mkdir -m 700 "$BUILD_CONTEXT"
if ! git archive --format=tar --output="$CONTEXT_ARCHIVE" "$TARGET_SHA" 2>/dev/null; then
  fail "Could not archive the requested target commit"
fi
chmod 600 "$CONTEXT_ARCHIVE"
if ! tar --extract --file="$CONTEXT_ARCHIVE" --directory="$BUILD_CONTEXT" 2>/dev/null; then
  fail "Could not materialize the target commit build context"
fi
[[ -f "${BUILD_CONTEXT}/cloudbuild.backend.yaml" ]] || fail "Target commit build config is missing"
[[ -f "${BUILD_CONTEXT}/Dockerfile.backend" ]] || fail "Target commit Dockerfile.backend is missing"
[[ -f "${BUILD_CONTEXT}/requirements.txt" ]] || fail "Target commit requirements.txt is missing"
BUILD_CONFIG="${BUILD_CONTEXT}/cloudbuild.backend.yaml"
BUILD_IGNORE_FILE="${BUILD_CONTEXT}/.gcloudignore"
cat >"${BUILD_IGNORE_FILE}" <<'GCLOUDIGNORE'
# Generated by the target commit's build helper. Keep the remote source closure explicit.
**
!.gcloudignore
!.dockerignore
!Dockerfile.backend
!cloudbuild.backend.yaml
!requirements.txt
!apps/
!apps/backend/
!apps/backend/backend/
!apps/backend/backend/**/
!apps/backend/backend/*.py
!apps/backend/backend/**/*.py
apps/backend/backend/**/*credential*.py
apps/backend/backend/**/*secret*.py
apps/backend/backend/**/*token*.py
GCLOUDIGNORE
chmod 600 "${BUILD_IGNORE_FILE}"

SUBMIT_OUTPUT="$(mktemp)"
if ! gcloud builds submit "${BUILD_CONTEXT}" \
  --project="${PROJECT_ID}" \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
  --config="${BUILD_CONFIG}" \
  --ignore-file="${BUILD_IGNORE_FILE}" \
  --substitutions="${SUBSTITUTIONS}" \
  --machine-type="${MACHINE_TYPE}" \
  --timeout="${BUILD_TIMEOUT}" \
  --async \
  --quiet \
  --format='value(id)' >"${SUBMIT_OUTPUT}" 2>/dev/null; then
  fail "Cloud Build submission failed"
fi

BUILD_ID="$(tr -d '\r\n' <"${SUBMIT_OUTPUT}")"
[[ "$BUILD_ID" =~ ^[A-Za-z0-9-]+$ ]] || fail "Cloud Build did not return a valid build identifier"

BUILD_STATUS=""
BUILD_DEADLINE=$((SECONDS + 1800))
POLL_DELAY=5
while :; do
  if ! BUILD_STATUS="$(gcloud builds describe "${BUILD_ID}" \
    --project="${PROJECT_ID}" \
    --format='value(status)' 2>/dev/null)"; then
    fail "Could not resolve the Cloud Build status"
  fi
  BUILD_STATUS="${BUILD_STATUS//$'\r'/}"
  BUILD_STATUS="${BUILD_STATUS//$'\n'/}"
  case "$BUILD_STATUS" in
    SUCCESS)
      break
      ;;
    FAILURE|INTERNAL_ERROR|TIMEOUT|CANCELLED|EXPIRED)
      fail "Cloud Build did not complete successfully"
      ;;
    QUEUED|WORKING|PENDING|FETCHING_SOURCE|BUILDING|STATUS_UNKNOWN|UNKNOWN|"")
      ;;
    *)
      fail "Cloud Build returned an unexpected status"
      ;;
  esac
  (( SECONDS < BUILD_DEADLINE )) || fail "Cloud Build timed out while waiting for completion"
  sleep "$POLL_DELAY"
  if (( POLL_DELAY < 30 )); then
    POLL_DELAY=$((POLL_DELAY * 2))
    (( POLL_DELAY > 30 )) && POLL_DELAY=30
  fi
done

BUILD_RESULT_DIGEST="$(gcloud builds describe "${BUILD_ID}" \
  --project="${PROJECT_ID}" \
  --format='value(results.images[0].digest)' 2>/dev/null | tr -d '\r\n')"
[[ "$BUILD_RESULT_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || \
  fail "Cloud Build returned no valid image digest"

REGISTRY_DIGEST="$(gcloud artifacts docker images describe "${IMAGE_TAG_URI}" \
  --project="${PROJECT_ID}" \
  --format='value(image_summary.digest)' 2>/dev/null | tr -d '\r\n')"
[[ "$REGISTRY_DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || \
  fail "Artifact Registry returned no valid image digest"
[[ "$BUILD_RESULT_DIGEST" == "$REGISTRY_DIGEST" ]] || \
  fail "Cloud Build result digest and registry digest mismatch"

NATIVE_PROVENANCE_OUTPUT="$(mktemp)"
chmod 600 "$NATIVE_PROVENANCE_OUTPUT"
if ! gcloud artifacts docker images describe "${IMAGE_NAME}@${REGISTRY_DIGEST}" \
  --project="${PROJECT_ID}" \
  --show-provenance \
  --format=json >"${NATIVE_PROVENANCE_OUTPUT}" 2>/dev/null; then
  fail "Artifact Registry native provenance lookup failed"
fi

if ! jq -e \
  --arg digest "$REGISTRY_DIGEST" \
  --arg digest_hex "${REGISTRY_DIGEST#sha256:}" \
  --arg image_uri "${IMAGE_NAME}@${REGISTRY_DIGEST}" \
  --arg source_repository "https://github.com/${REPOSITORY}" \
  --arg source_repository_git "git+https://github.com/${REPOSITORY}" \
  --arg target_sha "$TARGET_SHA" \
  --arg builder_workflow "$BUILDER_WORKFLOW" \
  --arg build_id "$BUILD_ID" \
  --arg native_build_type "https://cloud.google.com/build/gcb-buildtypes/google-worker/v1" \
  --arg native_builder "https://cloudbuild.googleapis.com/GoogleHostedWorker" \
  '
    def source_uri:
      (type == "string") and (
        . == $source_repository
        or . == $source_repository_git
        or . == ($source_repository_git + ".git")
        or . == ($source_repository_git + "@refs/heads/main")
        or . == ($source_repository_git + ".git@refs/heads/main")
        or . == ($source_repository_git + "@" + $target_sha)
        or . == ($source_repository_git + ".git@" + $target_sha)
        or . == ($source_repository + "@refs/heads/main")
        or . == ($source_repository + "@" + $target_sha)
      );

    if (.image_summary | type) != "object"
       or .image_summary.digest != $digest
       or .image_summary.fully_qualified_digest != $image_uri
       or (.provenance_summary | type) != "object"
       or (.provenance_summary.provenance | type) != "array" then
      false
    else
      [
        .provenance_summary.provenance[]
        | (.build // null) as $build
        | (($build.inTotoSlsaProvenanceV1 // $build.intotoSlsaProvenanceV1) // null) as $statement
        | select(($statement | type) == "object")
        | select($statement.predicateType == "https://slsa.dev/provenance/v1")
        | select(($statement.subject | type) == "array")
        | select(any($statement.subject[]; .digest.sha256 == $digest_hex))
        | select($statement.predicate.buildDefinition.buildType == $native_build_type)
        | select($statement.predicate.runDetails.builder.id == $native_builder)
        | ($statement.predicate.runDetails.metadata // null) as $metadata
        | select(($metadata | type) == "object")
        | select(any(
            [$metadata.invocationId?, $metadata.invocation_id?][];
            (type == "string") and (. == $build_id or endswith("/builds/" + $build_id))
          ))
        | ($statement.predicate.buildDefinition.resolvedDependencies // []) as $dependencies
        | select(($dependencies | type) == "array")
        # `gcloud builds submit <local-archive>` can omit SCM dependencies.
        # If Cloud Build reports one, it must identify this repository and SHA.
        | select(all(
            $dependencies[];
            ((.uri | type) != "string" or (.uri | startswith("git+") | not))
            or ((.uri | source_uri)
                and ((.digest.gitCommit // .digest.sha1 // "") == $target_sha))
          ))
        | ($statement.predicate.buildDefinition.externalParameters // null) as $external_parameters
        | select(($external_parameters | type) == "object")
        | ($external_parameters.substitutions // null) as $substitutions
        | select(($substitutions | type) == "object")
        | select(
            ($substitutions | has("_SOURCE_REPOSITORY"))
            and ($substitutions._SOURCE_REPOSITORY | type) == "string"
            and $substitutions._SOURCE_REPOSITORY == $source_repository
            and ($substitutions | has("_TARGET_SHA"))
            and ($substitutions._TARGET_SHA | type) == "string"
            and $substitutions._TARGET_SHA == $target_sha
            and ($substitutions | has("_BUILDER_WORKFLOW"))
            and ($substitutions._BUILDER_WORKFLOW | type) == "string"
            and $substitutions._BUILDER_WORKFLOW == $builder_workflow
          )
        | ($external_parameters.buildConfigSource // null) as $build_source
        | ($external_parameters.buildConfig // null) as $inline_build_config
        # Cloud Build v1 records exactly one build-config origin. A local
        # archived submit uses a non-empty base64 inline config; an SCM-backed
        # config must identify this repository, ref, and path.
        | select(
            ($build_source == null
             and ($inline_build_config | type) == "string"
             and ($inline_build_config | length) > 0)
            or ($inline_build_config == null
                and ($build_source | type) == "object"
                and ($build_source.repository | source_uri)
                and $build_source.ref == "refs/heads/main"
                and $build_source.path == "cloudbuild.backend.yaml")
          )
      ] as $matches
      | ($matches | length) == 1
    end' \
  "$NATIVE_PROVENANCE_OUTPUT" >/dev/null 2>&1; then
  fail "Cloud Build native provenance failed policy checks"
fi

NATIVE_PROVENANCE_DIGEST_HEX="$(sha256sum "$NATIVE_PROVENANCE_OUTPUT" | cut -d ' ' -f 1)"
[[ "$NATIVE_PROVENANCE_DIGEST_HEX" =~ ^[0-9a-f]{64}$ ]] || \
  fail "Cloud Build native provenance digest could not be resolved"
if ! gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >/dev/null 2>&1; then
  fail "Could not configure Artifact Registry Docker authentication"
fi
if ! docker pull --quiet "${IMAGE_NAME}@${REGISTRY_DIGEST}" >/dev/null 2>&1; then
  fail "Could not pull the exact backend image digest"
fi

if ! docker run --detach \
  --name "${SMOKE_CONTAINER}" \
  --env-file "${REPO_ROOT}/.env.ci" \
  --env FIRESTORE_PROJECT_ID=wordpack-ci \
  --env GCP_PROJECT_ID=wordpack-ci \
  --env FIRESTORE_EMULATOR_HOST=127.0.0.1:8081 \
  --publish 127.0.0.1:8080:8080 \
  "${IMAGE_NAME}@${REGISTRY_DIGEST}" >/dev/null 2>&1; then
  fail "Could not start the exact backend image for health smoke"
fi

smoke_passed=false
for _ in {1..30}; do
  if curl --fail --silent --show-error --connect-timeout 2 --max-time 5 --header 'Host: localhost' \
    http://127.0.0.1:8080/healthz >/dev/null 2>&1; then
    smoke_passed=true
    break
  fi
  if ! docker inspect --format='{{.State.Running}}' "${SMOKE_CONTAINER}" 2>/dev/null | grep -qx true; then
    break
  fi
  sleep 1
done
[[ "$smoke_passed" == true ]] || fail "Digest-bound backend health smoke failed"

log "Cloud Build result and Artifact Registry digest matched; digest health smoke passed."
{
  printf 'image_name=%s\n' "${IMAGE_NAME}"
  printf 'image_digest=%s\n' "${REGISTRY_DIGEST}"
  printf 'image_uri=%s@%s\n' "${IMAGE_NAME}" "${REGISTRY_DIGEST}"
  printf 'native_provenance_snapshot_sha256=sha256:%s\n' "${NATIVE_PROVENANCE_DIGEST_HEX}"
} >>"${GITHUB_OUTPUT}"
