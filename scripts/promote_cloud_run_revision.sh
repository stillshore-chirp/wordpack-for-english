#!/usr/bin/env bash
set -euo pipefail

log() {
  printf '[cloud-run-promotion] %s\n' "$*"
}

err() {
  printf 'Error: %s\n' "$*" >&2
}

usage() {
  cat <<'USAGE'
Promote a tagged Cloud Run revision with canary health checks and rollback.

Usage:
  scripts/promote_cloud_run_revision.sh [options]

Options:
  --project-id <id>          GCP project ID
  --region <region>          Cloud Run region
  --service <name>           Cloud Run service name
  --tag <tag>                Tag assigned to the no-traffic candidate revision
  --canary-percent <percent> Canary traffic percentage from 1 to 99 (default: 10)
  --attempts <count>         Health checks during the canary window (default: 7)
  --delay-seconds <seconds>  Delay between canary checks (default: 10)
  --requests-per-attempt <n> Production health requests per attempt (default: 10)
  --health-url <url>         Production health URL routed to this Cloud Run service
  --expected-version <value> Candidate DEPLOYMENT_VERSION expected in health JSON
  -h, --help                 Show this help
USAGE
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "Required command not found: $1"
    exit 1
  fi
}

PROJECT_ID=""
REGION=""
SERVICE_NAME=""
TRAFFIC_TAG=""
CANARY_PERCENT=10
HEALTH_ATTEMPTS=7
HEALTH_DELAY_SECONDS=10
HEALTH_REQUESTS_PER_ATTEMPT=10
HEALTH_URL=""
EXPECTED_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --service)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --tag)
      TRAFFIC_TAG="$2"
      shift 2
      ;;
    --canary-percent)
      CANARY_PERCENT="$2"
      shift 2
      ;;
    --attempts)
      HEALTH_ATTEMPTS="$2"
      shift 2
      ;;
    --delay-seconds)
      HEALTH_DELAY_SECONDS="$2"
      shift 2
      ;;
    --requests-per-attempt)
      HEALTH_REQUESTS_PER_ATTEMPT="$2"
      shift 2
      ;;
    --health-url)
      HEALTH_URL="$2"
      shift 2
      ;;
    --expected-version)
      EXPECTED_VERSION="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      err "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
done

for required_name in PROJECT_ID REGION SERVICE_NAME TRAFFIC_TAG HEALTH_URL EXPECTED_VERSION; do
  if [[ -z "${!required_name}" ]]; then
    err "${required_name} is required"
    exit 1
  fi
done

if [[ ! "$TRAFFIC_TAG" =~ ^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$ ]]; then
  err "--tag must be a lowercase DNS label of at most 63 characters"
  exit 1
fi
if [[ ! "$CANARY_PERCENT" =~ ^[0-9]+$ ]] || (( CANARY_PERCENT < 1 || CANARY_PERCENT > 99 )); then
  err "--canary-percent must be an integer from 1 to 99"
  exit 1
fi
if [[ ! "$HEALTH_ATTEMPTS" =~ ^[0-9]+$ ]] || (( HEALTH_ATTEMPTS < 1 )); then
  err "--attempts must be a positive integer"
  exit 1
fi
if [[ ! "$HEALTH_DELAY_SECONDS" =~ ^[0-9]+$ ]]; then
  err "--delay-seconds must be a non-negative integer"
  exit 1
fi
if [[ ! "$HEALTH_REQUESTS_PER_ATTEMPT" =~ ^[0-9]+$ ]] || (( HEALTH_REQUESTS_PER_ATTEMPT < 1 )); then
  err "--requests-per-attempt must be a positive integer"
  exit 1
fi
if [[ ! "$HEALTH_URL" =~ ^https:// ]]; then
  err "--health-url must use https://"
  exit 1
fi
if [[ ! "$EXPECTED_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]; then
  err "--expected-version must use 1-128 URL-safe marker characters"
  exit 1
fi

require_cmd gcloud
require_cmd curl
require_cmd python

SERVICE_JSON="$(gcloud run services describe "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format=json)"

PARSED_STATE="$(SERVICE_JSON="$SERVICE_JSON" python - "$TRAFFIC_TAG" <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["SERVICE_JSON"])
tag = sys.argv[1]
traffic = payload.get("status", {}).get("traffic", [])
candidate = next((entry for entry in traffic if entry.get("tag") == tag), None)
if not candidate:
    raise SystemExit(f"Candidate tag {tag!r} was not found in Cloud Run traffic status")

candidate_revision = candidate.get("revisionName")
candidate_percent = int(candidate.get("percent") or 0)
if not candidate_revision:
    raise SystemExit("Candidate tag is missing its revision name")
if candidate_percent != 0:
    raise SystemExit("Candidate revision already receives traffic; refusing to overwrite the baseline")

previous = {}
for entry in traffic:
    percent = int(entry.get("percent") or 0)
    if percent <= 0:
        continue
    revision = entry.get("revisionName")
    if not revision:
        raise SystemExit("An active traffic target is missing its revision name")
    previous[revision] = previous.get(revision, 0) + percent

if sum(previous.values()) != 100:
    raise SystemExit("Active Cloud Run traffic does not add up to 100 percent")

print(",".join(f"{revision}={percent}" for revision, percent in previous.items()))
PY
)"

ROLLBACK_TARGETS="$PARSED_STATE"
if [[ -z "$ROLLBACK_TARGETS" ]]; then
  err "Cloud Run traffic status could not be converted into a safe promotion plan"
  exit 1
fi

HEALTH_REQUEST_SEQUENCE=0
check_production_health() {
  local response observation probe_url
  HEALTH_REQUEST_SEQUENCE=$((HEALTH_REQUEST_SEQUENCE + 1))
  probe_url="${HEALTH_URL}?deployment_probe=${EXPECTED_VERSION}-${HEALTH_REQUEST_SEQUENCE}"
  if ! response="$(curl --fail --silent \
    --header 'Cache-Control: no-cache' \
    --connect-timeout 10 \
    --max-time 20 \
    "$probe_url")"; then
    err "Production health request failed"
    return 1
  fi
  if ! observation="$(HEALTH_RESPONSE="$response" python - "$EXPECTED_VERSION" <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["HEALTH_RESPONSE"])
is_health = payload.get("status") == "ok"
is_runtime_config = isinstance(payload.get("request_timeout_ms"), int)
if not (is_health or is_runtime_config):
    raise SystemExit("Production probe response did not match a supported health contract")
version = payload.get("deployment_version") or payload.get("version")
print("candidate" if version == sys.argv[1] else "other")
PY
  )"; then
    err "Production health response was invalid"
    return 1
  fi
  if [[ "$observation" == "candidate" ]]; then
    CANDIDATE_OBSERVED=true
  fi
}

TRAFFIC_CHANGED=false
rollback_on_error() {
  local status="${1:-$?}"
  trap - ERR INT TERM
  if [[ "$TRAFFIC_CHANGED" == true ]]; then
    err "Canary promotion failed; restoring the previous Cloud Run traffic allocation"
    if gcloud run services update-traffic "$SERVICE_NAME" \
      --project "$PROJECT_ID" \
      --region "$REGION" \
      --to-revisions "$ROLLBACK_TARGETS" \
      --format=none \
      --quiet; then
      log "Previous traffic allocation restored"
    else
      err "Automatic traffic rollback failed; manual rollback is required"
    fi
  fi
  exit "$status"
}

log "Tagged candidate is ready with 0% production traffic"

trap 'rollback_on_error $?' ERR
trap 'rollback_on_error 130' INT
trap 'rollback_on_error 143' TERM
TRAFFIC_CHANGED=true
log "Assigning ${CANARY_PERCENT}% traffic to the candidate"
gcloud run services update-traffic "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --to-tags "${TRAFFIC_TAG}=${CANARY_PERCENT}" \
  --format=none \
  --quiet

CANDIDATE_OBSERVED=false
for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt += 1)); do
  if (( attempt > 1 )); then
    sleep "$HEALTH_DELAY_SECONDS"
  fi
  log "Canary production health check ${attempt}/${HEALTH_ATTEMPTS}"
  for ((request = 1; request <= HEALTH_REQUESTS_PER_ATTEMPT; request += 1)); do
    check_production_health
  done
done
if [[ "$CANDIDATE_OBSERVED" != true ]]; then
  err "Canary traffic did not return the expected deployment version"
  false
fi

log "Canary remained healthy; assigning 100% traffic to the candidate"
gcloud run services update-traffic "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --to-tags "${TRAFFIC_TAG}=100" \
  --format=none \
  --quiet

CANDIDATE_OBSERVED=false
for ((request = 1; request <= HEALTH_REQUESTS_PER_ATTEMPT; request += 1)); do
  check_production_health
  [[ "$CANDIDATE_OBSERVED" == true ]] && break
  sleep 1
done
if [[ "$CANDIDATE_OBSERVED" != true ]]; then
  err "Promoted traffic did not return the expected deployment version"
  false
fi

TRAFFIC_CHANGED=false
trap - ERR INT TERM
log "Cloud Run candidate promotion completed"
