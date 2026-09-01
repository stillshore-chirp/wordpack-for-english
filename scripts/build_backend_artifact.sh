#!/usr/bin/env bash
set -euo pipefail

# Build the backend once in Cloud Build and exercise the exact registry digest.
# Image metadata and the two verification values are written to GITHUB_OUTPUT;
# build responses and raw credential-bearing command output stay out of workflow
# logs; submission failures emit only a fixed, allowlisted summary.
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
SUBMIT_ERROR=""
SUBMIT_FAILURE_MESSAGE="Cloud Build submission failed"
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
  if [[ -n "${SUBMIT_ERROR:-}" && -f "$SUBMIT_ERROR" ]]; then
    rm -f "$SUBMIT_ERROR" || true
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

bounded_submit_stderr_count() {
  local value="$1"
  local maximum="$2"
  [[ "$value" =~ ^[0-9]+$ ]] || value=0
  (( value > maximum )) && value="$maximum"
  printf '%s' "$value"
}

classify_cloud_build_submit_error() {
  local category=unknown
  if LC_ALL=C grep -Eqi -- 'PERMISSION_DENIED|permission[[:space:]]+denied|forbidden|access[[:space:]]+denied|(^|[^0-9])403([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=permission_denied
  elif LC_ALL=C grep -Eqi -- 'UNAUTHENTICATED|authentication|invalid[[:space:]]+(credential|token)|oauth|(^|[^0-9])401([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=authentication_failed
  elif LC_ALL=C grep -Eqi -- 'INVALID_ARGUMENT|invalid[[:space:]]+argument|bad[[:space:]]+request|(^|[^0-9])400([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=invalid_argument
  elif LC_ALL=C grep -Eqi -- 'NOT_FOUND|not[[:space:]]+found|(^|[^0-9])404([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=not_found
  elif LC_ALL=C grep -Eqi -- 'RESOURCE_EXHAUSTED|quota|rate[[:space:]]+limit|(^|[^0-9])429([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=quota_exhausted
  elif LC_ALL=C grep -Eqi -- 'DEADLINE_EXCEEDED|deadline|timed[[:space:]]+out|timeout|(^|[^0-9])504([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=deadline_exceeded
  elif LC_ALL=C grep -Eqi -- 'UNAVAILABLE|service[[:space:]]+unavailable|temporar(y|ily)|(^|[^0-9])502([^0-9]|$)|(^|[^0-9])503([^0-9]|$)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=service_unavailable
  elif LC_ALL=C grep -Eqi -- 'source[[:space:]_-]*(staging|upload)|staging|upload[[:space:]]+(source|archive)' "$SUBMIT_ERROR" 2>/dev/null; then
    category=source_staging
  elif LC_ALL=C grep -Eqi -- 'service[[:space:]_-]*account|serviceaccounts|iam\.service' "$SUBMIT_ERROR" 2>/dev/null; then
    category=service_account
  elif LC_ALL=C grep -Eqi -- 'storage|bucket|gs://|artifact[[:space:]]+registry' "$SUBMIT_ERROR" 2>/dev/null; then
    category=storage
  elif LC_ALL=C grep -Eqi -- 'cloud[[:space:]]+build|cloudbuild|builds[[:space:]]+submit' "$SUBMIT_ERROR" 2>/dev/null; then
    category=cloud_build
  fi
  printf '%s' "$category"
}

cloud_build_submit_stderr_matches() {
  LC_ALL=C grep -Eqi -- "$1" "$SUBMIT_ERROR" 2>/dev/null
}

detect_cloud_build_submit_surfaces() {
  local surfaces=""
  if cloud_build_submit_stderr_matches 'service[[:space:]_-]*account|serviceaccounts|iam[.]service'; then
    surfaces="${surfaces:+${surfaces},}service_account"
  fi
  if cloud_build_submit_stderr_matches 'CLOUD_LOGGING_ONLY|logging|logs?[[:space:]_-]*(bucket|configuration|mode)|cloud[[:space:]]+logging'; then
    surfaces="${surfaces:+${surfaces},}logging"
  fi
  if cloud_build_submit_stderr_matches 'requested[[:space:]_-]*verify|requestedVerifyOption|verify[[:space:]_-]*(option|setting)|verification|verified'; then
    surfaces="${surfaces:+${surfaces},}requested_verify"
  fi
  if cloud_build_submit_stderr_matches 'substitution|_IMAGE_URI|_SOURCE_REPOSITORY|_TARGET_SHA|_BUILDER_WORKFLOW'; then
    surfaces="${surfaces:+${surfaces},}substitutions"
  fi
  if cloud_build_submit_stderr_matches '(^|[^[:alnum:]_])source([^[:alnum:]_]|$)|source[[:space:]_-]*(context|archive|upload|staging)|gcs|gs://'; then
    surfaces="${surfaces:+${surfaces},}source"
  fi
  if cloud_build_submit_stderr_matches 'image(s)?|container[[:space:]_-]*(image|registry)|artifact[[:space:]_-]*registry|docker'; then
    surfaces="${surfaces:+${surfaces},}images"
  fi
  if cloud_build_submit_stderr_matches 'step(s)?|build[[:space:]_-]*step|args'; then
    surfaces="${surfaces:+${surfaces},}steps"
  fi
  if cloud_build_submit_stderr_matches 'machine[[:space:]_-]*type|machineType|worker[[:space:]_-]*(pool|type)'; then
    surfaces="${surfaces:+${surfaces},}machine_type"
  fi
  if cloud_build_submit_stderr_matches 'timeout|deadline|timed[[:space:]]+out'; then
    surfaces="${surfaces:+${surfaces},}timeout"
  fi
  if cloud_build_submit_stderr_matches 'location|region|zone|multi[[:space:]_-]*region'; then
    surfaces="${surfaces:+${surfaces},}location"
  fi
  if cloud_build_submit_stderr_matches '(^|[^[:alnum:]_])options?([^[:alnum:]_]|$)|build[[:space:]_-]*options?|buildOptions'; then
    surfaces="${surfaces:+${surfaces},}options"
  fi
  printf '%s' "${surfaces:-none}"
}

classify_cloud_build_submit_reason() {
  local category="$1"
  if cloud_build_submit_stderr_matches 'service[[:space:]_-]*account' && \
    cloud_build_submit_stderr_matches 'logging|logs?[[:space:]_-]*bucket|CLOUD_LOGGING_ONLY'; then
    printf 'user_service_account_logging'
  elif cloud_build_submit_stderr_matches 'service[[:space:]_-]*account' && \
    cloud_build_submit_stderr_matches 'format|email|identifier|invalid|malformed|account[[:space:]_-]*id'; then
    printf 'service_account_format'
  elif cloud_build_submit_stderr_matches 'requested[[:space:]_-]*verify|requestedVerifyOption|verify[[:space:]_-]*(option|setting)|verification|verified'; then
    printf 'requested_verify'
  elif cloud_build_submit_stderr_matches 'substitution|_IMAGE_URI|_SOURCE_REPOSITORY|_TARGET_SHA|_BUILDER_WORKFLOW'; then
    printf 'substitution'
  elif cloud_build_submit_stderr_matches '(^|[^[:alnum:]_])source([^[:alnum:]_]|$)|source[[:space:]_-]*(context|archive|upload|staging)|gcs|gs://'; then
    printf 'source'
  elif [[ "$category" == invalid_argument ]]; then
    printf 'generic_invalid'
  else
    printf 'unknown'
  fi
}

detect_cloud_build_submit_http_status() {
  local status
  for status in 400 401 403 404 409 429 500 502 503 504; do
    if LC_ALL=C grep -Eqi -- "(HTTP|status|code|error)[^0-9]{0,8}$status([^0-9]|$)" "$SUBMIT_ERROR" 2>/dev/null; then
      printf '%s' "$status"
      return 0
    fi
  done
  printf 'none'
}

print_cloud_build_submit_summary() {
  local exit_status="$1"
  local stderr_lines=""
  local stderr_bytes=""
  local category=""
  local http_status=""
  local surfaces=""
  local reason=""

  stderr_lines="$(wc -l <"$SUBMIT_ERROR" | tr -d '[:space:]')"
  stderr_bytes="$(wc -c <"$SUBMIT_ERROR" | tr -d '[:space:]')"
  stderr_lines="$(bounded_submit_stderr_count "$stderr_lines" 999999)"
  stderr_bytes="$(bounded_submit_stderr_count "$stderr_bytes" 999999)"
  category="$(classify_cloud_build_submit_error)"
  http_status="$(detect_cloud_build_submit_http_status)"
  surfaces="$(detect_cloud_build_submit_surfaces)"
  reason="$(classify_cloud_build_submit_reason "$category")"

  printf 'Cloud Build submit failure (sanitized):\n' >&2
  printf '  exit_status=%s\n' "$exit_status" >&2
  printf '  stderr_lines=%s stderr_bytes=%s\n' "$stderr_lines" "$stderr_bytes" >&2
  printf '  category=%s http_status=%s surfaces=%s reason=%s\n' \
    "$category" "$http_status" "$surfaces" "$reason" >&2
}

# Build only the requested commit. The archive is intentionally made from the
# Git object database instead of the checkout, so staged, dirty, ignored, and
# untracked files (including generated env/secret material) cannot enter the
# remote build context.
BUILD_CONTEXT_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/wordpack-backend-build.XXXXXX")"
chmod 700 "$BUILD_CONTEXT_ROOT"
BUILD_CONTEXT="${BUILD_CONTEXT_ROOT}/context"
CONTEXT_ARCHIVE="${BUILD_CONTEXT_ROOT}/context.tar"
CONTEXT_TREE="${BUILD_CONTEXT_ROOT}/context-tree"
CONTEXT_FILES="${BUILD_CONTEXT_ROOT}/context-files"
mkdir -m 700 "$BUILD_CONTEXT"
ARCHIVE_PATHS=(
  .dockerignore
  Dockerfile.backend
  cloudbuild.backend.yaml
  requirements.txt
  'apps/backend/backend/*.py'
  'apps/backend/backend/**/*.py'
)
TREE_PATHS=(
  .dockerignore
  Dockerfile.backend
  cloudbuild.backend.yaml
  requirements.txt
  apps/backend/backend
)
ARCHIVE_EXCLUDE_PATHS=(
  ':(exclude,icase,glob)apps/backend/backend/**/*credential*.py'
  ':(exclude,icase,glob)apps/backend/backend/**/*secret*.py'
  ':(exclude,icase,glob)apps/backend/backend/**/*token*.py'
)
if ! git archive --format=tar --output="$CONTEXT_ARCHIVE" "$TARGET_SHA" -- \
  "${ARCHIVE_PATHS[@]}" "${ARCHIVE_EXCLUDE_PATHS[@]}" 2>/dev/null; then
  fail "Could not archive the requested target commit"
fi
chmod 600 "$CONTEXT_ARCHIVE"

# Build a NUL-delimited list of regular blobs from the same target and
# allowlist.  Extracting only these members turns the archive into a physical
# context and keeps excluded or malformed symlinks out of the gcloud walk.
if ! git ls-tree -r -z --format='%(objectmode)%x09%(path)' "$TARGET_SHA" -- \
  "${TREE_PATHS[@]}" >"$CONTEXT_TREE" 2>/dev/null; then
  fail "Could not resolve the target commit build context"
fi
: >"$CONTEXT_FILES"
while IFS=$'\t' read -r -d '' object_mode path; do
  case "$object_mode" in
    100644|100755)
      case "$path" in
        .dockerignore|Dockerfile.backend|cloudbuild.backend.yaml|requirements.txt)
          ;;
        apps/backend/backend/*.py)
          ;;
        *)
          continue
          ;;
      esac
      case "$path" in
        apps/backend/backend/*[Cc][Rr][Ee][Dd][Ee][Nn][Tt][Ii][Aa][Ll]*.py|apps/backend/backend/*[Ss][Ee][Cc][Rr][Ee][Tt]*.py|apps/backend/backend/*[Tt][Oo][Kk][Ee][Nn]*.py)
          continue
          ;;
      esac
      printf '%s\0' "$path" >>"$CONTEXT_FILES"
      ;;
  esac
done <"$CONTEXT_TREE"
[[ -s "$CONTEXT_FILES" ]] || fail "Target commit build context contains no regular files"

if ! tar --extract --file="$CONTEXT_ARCHIVE" --directory="$BUILD_CONTEXT" \
  --null --files-from="$CONTEXT_FILES" --no-recursion --no-same-owner --no-same-permissions 2>/dev/null; then
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
SUBMIT_ERROR="$(mktemp "${BUILD_CONTEXT_ROOT}/cloud-build-submit.XXXXXX")"
chmod 600 "$SUBMIT_ERROR"
if gcloud builds submit "${BUILD_CONTEXT}" \
  --project="${PROJECT_ID}" \
  --service-account="projects/${PROJECT_ID}/serviceAccounts/${BUILD_SERVICE_ACCOUNT}" \
  --config="${BUILD_CONFIG}" \
  --ignore-file="${BUILD_IGNORE_FILE}" \
  --substitutions="${SUBSTITUTIONS}" \
  --machine-type="${MACHINE_TYPE}" \
  --timeout="${BUILD_TIMEOUT}" \
  --async \
  --quiet \
  --format='value(id)' >"${SUBMIT_OUTPUT}" 2>"${SUBMIT_ERROR}"; then
  :
else
  submit_exit_status=$?
  print_cloud_build_submit_summary "$submit_exit_status"
  fail "$SUBMIT_FAILURE_MESSAGE"
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

    def has_expected_substitutions($substitutions):
      ($substitutions | type) == "object"
      and ($substitutions | has("_SOURCE_REPOSITORY"))
      and ($substitutions._SOURCE_REPOSITORY | type) == "string"
      and $substitutions._SOURCE_REPOSITORY == $source_repository
      and ($substitutions | has("_TARGET_SHA"))
      and ($substitutions._TARGET_SHA | type) == "string"
      and $substitutions._TARGET_SHA == $target_sha
      and ($substitutions | has("_BUILDER_WORKFLOW"))
      and ($substitutions._BUILDER_WORKFLOW | type) == "string"
      and $substitutions._BUILDER_WORKFLOW == $builder_workflow;

    # `// null` treats JSON false as absent in jq. Preserve explicitly
    # malformed values so origin selection rejects them fail-closed.
    def field_or_null($object; $name):
      if ($object | has($name)) then $object[$name] else null end;

    def is_scm_uri:
      startswith("git+")
      or test("^https?://github\\.com(?:/|$)")
      or test("^git://github\\.com(?:/|$)")
      or test("^ssh://(?:git@)?github\\.com(?:/|$)");

    def has_scm_digest($dependency):
      if ($dependency.digest | type) != "object" then
        false
      else
        ($dependency.digest | has("gitCommit"))
        or ($dependency.digest | has("sha1"))
      end;

    def scm_digest_matches($dependency):
      if ($dependency.digest | type) != "object" then
        false
      elif (($dependency.digest | has("gitCommit"))
            and ($dependency.digest | has("sha1"))) then
        ($dependency.digest.gitCommit | type) == "string"
        and ($dependency.digest.sha1 | type) == "string"
        and $dependency.digest.gitCommit == $target_sha
        and $dependency.digest.sha1 == $target_sha
      elif ($dependency.digest | has("gitCommit")) then
        ($dependency.digest.gitCommit | type) == "string"
        and $dependency.digest.gitCommit == $target_sha
      elif ($dependency.digest | has("sha1")) then
        ($dependency.digest.sha1 | type) == "string"
        and $dependency.digest.sha1 == $target_sha
      else
        false
      end;

    # Keep non-SCM dependencies compatible with Cloud Build resource forms
    # while routing GitHub/SCM-shaped inputs through the exact source policy.
    def is_allowed_non_scm_uri:
      # jq `$` can match before a terminal newline; reject all whitespace
      # before applying the URI shape checks.
      (test("[[:space:]]") | not)
      and (
        test("^gs://[^/[:space:]]+(?:/[^[:space:]]*)?$")
        or test("^(?:https?://)?(?:[a-z0-9-]+\\.)?gcr\\.io/[^[:space:]]+$")
        or test("^(?:https?://)?[a-z0-9][a-z0-9-]*-docker\\.pkg\\.dev/[^[:space:]]+$")
      );

    def dependency_matches($dependency):
      if (($dependency.uri | is_scm_uri) or has_scm_digest($dependency)) then
        ($dependency.uri | source_uri)
        and scm_digest_matches($dependency)
      else
        ($dependency.uri | is_allowed_non_scm_uri)
      end;

    def decode_inline_build_config:
      if (type != "string"
          or length == 0
          or (test("^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$") | not))
      then error("invalid inline build config encoding")
      else
        . as $encoded
        | ($encoded | @base64d) as $decoded
        | if (($decoded | @base64) != $encoded) then
            error("non-canonical inline build config encoding")
          else
            ($decoded | fromjson)
          end
      end;

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
        | (field_or_null($statement.predicate.buildDefinition; "resolvedDependencies")) as $raw_dependencies
        | (if $raw_dependencies == null then [] else $raw_dependencies end) as $dependencies
        | select(($dependencies | type) == "array")
        # `gcloud builds submit <local-archive>` can omit SCM dependencies.
        # If Cloud Build reports one, it must identify this repository and SHA.
        | select(all(
            $dependencies[];
            . as $dependency
            | if ($dependency | type) != "object" then
                false
              elif ($dependency.uri | type) != "string"
                   or ($dependency.uri | length) == 0 then
                false
              else
                dependency_matches($dependency)
              end
          ))
        | ($statement.predicate.buildDefinition.externalParameters // null) as $external_parameters
        | select(($external_parameters | type) == "object")
        | (field_or_null($external_parameters; "substitutions")) as $external_substitutions
        | (field_or_null($external_parameters; "buildConfigSource")) as $build_source
        | (field_or_null($external_parameters; "buildConfig")) as $inline_build_config
        # Cloud Build v1 records exactly one build-config origin. A local
        # archived submit uses a non-empty base64 inline config; an SCM-backed
        # config must identify this repository, ref, and path.
        | if ($build_source == null
             and ($inline_build_config | type) == "string"
             and ($inline_build_config | length) > 0) then
            ($inline_build_config | decode_inline_build_config) as $decoded_build_config
            | select(($decoded_build_config | type) == "object")
            | ($decoded_build_config.substitutions // null) as $inline_substitutions
            | select(has_expected_substitutions($inline_substitutions))
            # A local archive may report caller substitutions outside the
            # inline config too. Empty/null is the observed shape; if values
            # are present, they must independently match the same policy.
            | select(
                $external_substitutions == null
                or (($external_substitutions | type) == "object"
                    and ($external_substitutions | length) == 0)
                or has_expected_substitutions($external_substitutions)
              )
          elif ($inline_build_config == null
                and ($build_source | type) == "object"
                and ($build_source.repository | source_uri)
                and $build_source.ref == "refs/heads/main"
                and $build_source.path == "cloudbuild.backend.yaml") then
            select(has_expected_substitutions($external_substitutions))
          else
            empty
          end
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
