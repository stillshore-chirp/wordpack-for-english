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
  --health-path <path>       Candidate health path (default: /healthz)
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
HEALTH_PATH="/healthz"

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
    --health-path)
      HEALTH_PATH="$2"
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

for required_name in PROJECT_ID REGION SERVICE_NAME TRAFFIC_TAG; do
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
if [[ ! "$HEALTH_PATH" =~ ^/ ]]; then
  err "--health-path must start with /"
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

candidate_url = candidate.get("url")
candidate_revision = candidate.get("revisionName")
candidate_percent = int(candidate.get("percent") or 0)
if not candidate_url or not candidate_revision:
    raise SystemExit("Candidate tag is missing its URL or revision name")
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

print(candidate_url)
print(",".join(f"{revision}={percent}" for revision, percent in previous.items()))
PY
)"

mapfile -t STATE_LINES <<< "$PARSED_STATE"
CANDIDATE_URL="${STATE_LINES[0]:-}"
ROLLBACK_TARGETS="${STATE_LINES[1]:-}"
if [[ -z "$CANDIDATE_URL" || -z "$ROLLBACK_TARGETS" ]]; then
  err "Cloud Run traffic status could not be converted into a safe promotion plan"
  exit 1
fi

check_candidate_health() {
  local http_status
  http_status="$(curl --silent \
    --output /dev/null \
    --write-out '%{http_code}' \
    --connect-timeout 10 \
    --max-time 20 \
    "${CANDIDATE_URL}${HEALTH_PATH}")"
  if [[ ! "$http_status" =~ ^2[0-9][0-9]$ ]]; then
    err "Candidate health check failed with a non-success response"
    return 1
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

log "Checking the tagged candidate before assigning production traffic"
check_candidate_health

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

for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt += 1)); do
  if (( attempt > 1 )); then
    sleep "$HEALTH_DELAY_SECONDS"
  fi
  log "Canary health check ${attempt}/${HEALTH_ATTEMPTS}"
  check_candidate_health
done

log "Canary remained healthy; assigning 100% traffic to the candidate"
gcloud run services update-traffic "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --to-tags "${TRAFFIC_TAG}=100" \
  --format=none \
  --quiet

TRAFFIC_CHANGED=false
trap - ERR INT TERM
log "Cloud Run candidate promotion completed"
