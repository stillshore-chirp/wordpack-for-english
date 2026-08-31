#!/usr/bin/env bash
set -euo pipefail

# Verify both signed statements for the immutable backend image. The gh JSON
# response is parsed locally and never emitted, so attestation payloads do not
# become workflow log data.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

err() { printf 'Error: %s\n' "$*" >&2; }
fail() { err "$*"; exit 1; }
require_cmd() { command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"; }
require_value() { [[ $# -ge 2 && -n "$2" ]] || fail "$1 requires a non-empty value"; }

usage() {
  cat <<'USAGE'
Verify provenance and SPDX attestations for an immutable backend image.

Usage:
  scripts/verify_backend_artifact_attestations.sh [options]

Options:
  --image-uri <uri>             Fully-qualified image URI ending in @sha256:<64 hex>
  --repository <owner/repo>     GitHub repository identity
  --target-sha <sha>            Expected source commit SHA
  --source-digest <sha>         SHA of the source repository bound to the attestation
  --signer-digest <sha>         SHA of the signed workflow revision
  --native-provenance-snapshot-sha256 <digest>
                                SHA-256 of the validated Cloud Build provenance JSON snapshot
  --builder-workflow <uri>      Exact production workflow identity
  --provenance <path>           Local SLSA v1 predicate file
  --sbom <path>                 Local SPDX JSON file
  -h, --help                    Show this help
USAGE
}

IMAGE_URI=""
REPOSITORY=""
TARGET_SHA=""
SOURCE_DIGEST=""
SIGNER_DIGEST=""
NATIVE_PROVENANCE_SNAPSHOT_SHA256=""
BUILDER_WORKFLOW=""
PROVENANCE_FILE=""
SBOM_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --image-uri)
      require_value "$@"
      IMAGE_URI="$2"
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
    --source-digest)
      require_value "$@"
      SOURCE_DIGEST="$2"
      shift 2
      ;;
    --signer-digest)
      require_value "$@"
      SIGNER_DIGEST="$2"
      shift 2
      ;;
    --native-provenance-snapshot-sha256)
      require_value "$@"
      NATIVE_PROVENANCE_SNAPSHOT_SHA256="$2"
      shift 2
      ;;
    --builder-workflow)
      require_value "$@"
      BUILDER_WORKFLOW="$2"
      shift 2
      ;;
    --provenance)
      require_value "$@"
      PROVENANCE_FILE="$2"
      shift 2
      ;;
    --sbom)
      require_value "$@"
      SBOM_FILE="$2"
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

[[ "$IMAGE_URI" =~ ^[a-z0-9]+(-[a-z0-9]+)*-docker\.pkg\.dev/[a-z][a-z0-9-]{4,28}[a-z0-9]/[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}$ ]] || \
  fail "image URI must be a fully-qualified Artifact Registry digest"
[[ "$REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || \
  fail "repository must use the owner/repository form"
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]] || fail "target SHA must be a lowercase 40-character commit SHA"
[[ "$SOURCE_DIGEST" =~ ^[0-9a-fA-F]{40}$ ]] || \
  fail "source digest must be a 40-character commit SHA"
[[ "$SIGNER_DIGEST" =~ ^[0-9a-fA-F]{40}$ ]] || \
  fail "signer digest must be a 40-character commit SHA"
[[ "$NATIVE_PROVENANCE_SNAPSHOT_SHA256" =~ ^sha256:[0-9a-f]{64}$ ]] || \
  fail "native provenance snapshot SHA-256 must use sha256:<64 lowercase hex>"
SOURCE_DIGEST="${SOURCE_DIGEST,,}"
SIGNER_DIGEST="${SIGNER_DIGEST,,}"
if [[ -n "${GITHUB_SHA:-}" ]]; then
  RUNTIME_GITHUB_SHA="${GITHUB_SHA,,}"
  [[ "$RUNTIME_GITHUB_SHA" == "$SOURCE_DIGEST" ]] || \
    fail "source digest does not match the runtime GITHUB_SHA"
fi
if [[ -n "${GITHUB_WORKFLOW_SHA:-}" ]]; then
  RUNTIME_GITHUB_WORKFLOW_SHA="${GITHUB_WORKFLOW_SHA,,}"
  [[ "$RUNTIME_GITHUB_WORKFLOW_SHA" == "$SIGNER_DIGEST" ]] || \
    fail "signer digest does not match the runtime GITHUB_WORKFLOW_SHA"
fi
EXPECTED_BUILDER_WORKFLOW="https://github.com/${REPOSITORY}/.github/workflows/deploy-production.yml@refs/heads/main"
[[ "$BUILDER_WORKFLOW" == "$EXPECTED_BUILDER_WORKFLOW" ]] || \
  fail "builder workflow must be the pinned production workflow on main"
[[ -f "$PROVENANCE_FILE" ]] || fail "provenance predicate file is missing"
[[ -f "$SBOM_FILE" ]] || fail "SPDX SBOM file is missing"
[[ -n "${GH_TOKEN:-}" ]] || fail "GH_TOKEN is required for attestation verification"

require_cmd gh
require_cmd jq

IMAGE_NAME="${IMAGE_URI%@*}"
IMAGE_DIGEST="${IMAGE_URI##*@}"
DIGEST_HEX="${IMAGE_DIGEST#sha256:}"
SOURCE_REPOSITORY="https://github.com/${REPOSITORY}"
SIGNER_WORKFLOW="${REPOSITORY}/.github/workflows/deploy-production.yml"
BUILD_TYPE="${BUILDER_WORKFLOW}#backend-cloud-build-v1"
BUILDER_ID="${BUILDER_WORKFLOW}"
UNDERLYING_BUILDER="https://cloudbuild.googleapis.com/GoogleHostedWorker"
TMP_FILES=()

cleanup() {
  local previous_status=$?
  local path
  for path in "${TMP_FILES[@]}"; do
    [[ -z "$path" ]] || rm -f "$path" || true
  done
  return "$previous_status"
}
trap cleanup EXIT

# Validate the local files before querying GitHub; this binds the checks to the
# same digest and source target that the deploy job passes to this helper.
jq -e \
  --arg repository "$SOURCE_REPOSITORY" \
  --arg target "$TARGET_SHA" \
  --arg workflow "$BUILDER_WORKFLOW" \
  --arg build_type "$BUILD_TYPE" \
  --arg builder "$BUILDER_ID" \
  --arg underlying_builder "$UNDERLYING_BUILDER" \
  --arg native_snapshot "$NATIVE_PROVENANCE_SNAPSHOT_SHA256" \
  '.buildDefinition.externalParameters.sourceRepository == $repository
   and .buildDefinition.externalParameters.targetSha == $target
   and .buildDefinition.externalParameters.builderWorkflow == $workflow
   and .buildDefinition.externalParameters.underlyingBuilder == $underlying_builder
   and .buildDefinition.externalParameters.cloudBuildProvenance == "required"
   and .buildDefinition.externalParameters.nativeProvenanceSnapshotSha256 == $native_snapshot
   and .buildDefinition.buildType == $build_type
   and any(.buildDefinition.resolvedDependencies[]?;
     .uri == $repository and .digest.gitCommit == $target)
   and .runDetails.builder.id == $builder' \
  "$PROVENANCE_FILE" >/dev/null || fail "local provenance predicate failed policy checks"

jq -e \
  '.spdxVersion == "SPDX-2.3"
   and (.name | type == "string" and length > 0)' \
  "$SBOM_FILE" >/dev/null || fail "local SBOM is not a valid SPDX JSON document"

verify_attestation() {
  local predicate_type="$1"
  local attestation_json
  attestation_json="$(mktemp)"
  TMP_FILES+=("$attestation_json")

  # Keep the exact policy flags on both provenance and SPDX verification calls.
  if ! gh attestation verify "oci://${IMAGE_URI}" \
    --repo "$REPOSITORY" \
    --signer-workflow "$SIGNER_WORKFLOW" \
    --source-ref refs/heads/main \
    --source-digest "$SOURCE_DIGEST" \
    --signer-digest "$SIGNER_DIGEST" \
    --deny-self-hosted-runners \
    --predicate-type "$predicate_type" \
    --format=json >"$attestation_json" 2>/dev/null; then
    fail "GitHub attestation verification failed"
  fi

  if [[ "$predicate_type" == "https://slsa.dev/provenance/v1" ]]; then
    jq -e \
      --arg image_name "$IMAGE_NAME" \
      --arg digest "$DIGEST_HEX" \
      --arg repository "$SOURCE_REPOSITORY" \
      --arg target "$TARGET_SHA" \
      --arg workflow "$BUILDER_WORKFLOW" \
      --arg build_type "$BUILD_TYPE" \
      --arg builder "$BUILDER_ID" \
      --arg underlying_builder "$UNDERLYING_BUILDER" \
      --arg native_snapshot "$NATIVE_PROVENANCE_SNAPSHOT_SHA256" \
      'any(.[]?;
        .verificationResult.statement.predicateType == "https://slsa.dev/provenance/v1"
        and any(.verificationResult.statement.subject[]?;
          .name == $image_name and .digest.sha256 == $digest)
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.sourceRepository == $repository
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.targetSha == $target
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.builderWorkflow == $workflow
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.underlyingBuilder == $underlying_builder
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.cloudBuildProvenance == "required"
        and .verificationResult.statement.predicate.buildDefinition.externalParameters.nativeProvenanceSnapshotSha256 == $native_snapshot
        and .verificationResult.statement.predicate.buildDefinition.buildType == $build_type
        and any(.verificationResult.statement.predicate.buildDefinition.resolvedDependencies[]?;
          .uri == $repository and .digest.gitCommit == $target)
        and .verificationResult.statement.predicate.runDetails.builder.id == $builder)' \
      "$attestation_json" >/dev/null || fail "provenance attestation policy checks failed"
  else
    jq -e \
      --arg image_name "$IMAGE_NAME" \
      --arg digest "$DIGEST_HEX" \
      'any(.[]?;
        .verificationResult.statement.predicateType == "https://spdx.dev/Document/v2.3"
        and any(.verificationResult.statement.subject[]?;
          .name == $image_name and .digest.sha256 == $digest)
        and .verificationResult.statement.predicate.spdxVersion == "SPDX-2.3")' \
      "$attestation_json" >/dev/null || fail "SPDX attestation policy checks failed"
  fi
}

verify_attestation "https://slsa.dev/provenance/v1"
verify_attestation "https://spdx.dev/Document/v2.3"
