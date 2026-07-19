#!/usr/bin/env bash
set -euo pipefail

# このスクリプトは Cloud Run へのデプロイを自動化し、
# ざっくり次の 3 段階をまとめて実行します。
#   1) `.env.deploy` などから環境変数を読み込み、欠けている設定がないか確認する
#   2) Python 側の設定ローダーを呼び出して、値の形式や必須項目をバリデーションする
#   3) Cloud Build でコンテナイメージをビルドし、Cloud Run へデプロイする
# `--dry-run` を付けると 1) と 2) だけを実行し、実際のビルド/デプロイは行いません。
# 「設定だけ先にチェックしたい」ときは dry-run を使う、というイメージです。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# log: デプロイの進捗を1行ずつ表示するシンプルなロガーです。
# いつ・どの処理を実行しているかを追いやすくするために使います。
log() {
  printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*"
}

# err: エラーを標準エラー出力へ出しつつ、分かりやすいメッセージで止めます。
# 「何が足りないか」を人間がすぐ読めるようにするための小さなヘルパーです。
err() {
  printf 'Error: %s\n' "$*" >&2
}

usage() {
  cat <<'USAGE'
Cloud Run deployment helper

Usage:
  scripts/deploy_cloud_run.sh [options]

Options:
  --project-id <id>          GCP Project ID (fallback: PROJECT_ID in env file)
  --region <region>          Artifact Registry / Cloud Run region
  --service <name>           Cloud Run service name (default: wordpack-backend)
  --artifact-repo <path>     Artifact Registry repo path (default: wordpack/backend)
  --image-tag <tag>          Image tag (default: git rev-parse --short HEAD)
  --build-arg KEY=VALUE      Additional docker build arg (repeatable)
  --env-file <path>          Explicit env file (default: .env.deploy or .env)
  --run-timeout <duration>   Cloud Run request timeout, e.g. 360s, 10m (default: use existing service setting)
  --min-instances <count>    Cloud Run minimum instances, e.g. 0, 1, default (default: keep current)
  --no-cpu-throttling        Disable CPU throttling to allow background work after responses (default: keep current)
  --no-traffic               Deploy a tagged revision without changing production traffic
  --traffic-tag <tag>        Tag for a no-traffic candidate revision
  --generate-secret          Generate SESSION_SECRET_KEY via openssl if missing
  --secret-length <bytes>    Byte size for openssl rand -base64 (default: 48)
  --machine-type <type>      Cloud Build machine type (default: e2-medium)
  --timeout <duration>       Cloud Build timeout, e.g. 30m
  --dry-run                  Validate config only (skip gcloud build/deploy)
  -h, --help                 Show this help
USAGE
}

# require_cmd: 必要なコマンドがインストールされているかを確認します。
# 例: gcloud / firebase / python / git などが無いと、途中でコケて原因が分かりにくく
# なるため、最初にチェックして「このコマンドを入れてください」と案内します。
require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "Required command not found: $cmd"
    exit 1
  fi
}

# ensure_gcloud: gcloud を使う前に一度だけ存在確認をします。
# gcloud を複数回チェックしないよう、フラグで一度きりにしています。
ensure_gcloud() {
  if [[ "${GCLOUD_CMD_CHECKED:-false}" != true ]]; then
    require_cmd gcloud
    GCLOUD_CMD_CHECKED=true
  fi
}

# get_gcloud_config_value: gcloud の設定から project や region を読み取るヘルパーです。
# `.env.deploy` に書かれていない場合でも、gcloud の既定値をうまく再利用できます。
get_gcloud_config_value() {
  local key="$1"
  ensure_gcloud
  local value=""
  if value="$(gcloud config get-value "$key" --format='value(.)' 2>/dev/null)"; then
    value="$(printf '%s' "$value" | tr -d '\r\n')"
  else
    value=""
  fi
  if [[ "$value" == "(unset)" ]]; then
    value=""
  fi
  printf '%s' "$value"
}

# add_env_key: Cloud Run に渡す環境変数の「キー一覧」を集める関数です。
# 実際の値は `.env.deploy` から読み込みますが、ここでは「どのキーを送るか」だけ
# を覚えておき、あとで YAML 形式の env ファイルを組み立てるときに使います。
add_env_key() {
  local key="$1"
  [[ -z "$key" ]] && return 0
  DEPLOY_ENV_KEYS["$key"]=1
}

# escape_yaml_value: Cloud Run の `--env-vars-file` へ値を書き込むときに使います。
# YAML は改行や " に特別な意味があるため、ここで安全な形（1行の文字列）に
# 変換してからファイルに出力します。
escape_yaml_value() {
  local raw sanitized
  raw="$(printf '%s' "$1" | tr -d '\r\n')"
  sanitized="${raw//\\/\\\\}"
  sanitized="${sanitized//"/\\"}"
  printf '%s' "$sanitized"
}

ENV_FILE=""
PROJECT_ID_ARG=""
REGION_ARG=""
SERVICE_NAME="wordpack-backend"
ARTIFACT_REPOSITORY="wordpack/backend"
IMAGE_TAG=""
SECRET_LENGTH=48
GENERATE_SECRET=false
DRY_RUN=false
MACHINE_TYPE="e2-medium"
BUILD_TIMEOUT="30m"
RUN_TIMEOUT_ARG=""
MIN_INSTANCES_ARG=""
NO_CPU_THROTTLING=false
NO_TRAFFIC=false
TRAFFIC_TAG=""
declare -a EXTRA_BUILD_ARGS=()
declare -a CONFIG_PYTHON_CMD=()

declare -A DEPLOY_ENV_KEYS=()
declare -a IGNORE_DEPLOY_KEYS=(PROJECT_ID REGION CLOUD_RUN_SERVICE ARTIFACT_REPOSITORY IMAGE_TAG MACHINE_TYPE BUILD_TIMEOUT CLOUD_RUN_MIN_INSTANCES)
declare -a REQUIRED_DEPLOY_KEYS=(ADMIN_EMAIL_ALLOWLIST SESSION_SECRET_KEY CORS_ALLOWED_ORIGINS TRUSTED_PROXY_IPS ALLOWED_HOSTS)
GCLOUD_CMD_CHECKED=false

validate_min_instances() {
  local value="$1"
  [[ -z "$value" || "$value" == "default" ]] && return 0
  if [[ "$value" =~ ^[0-9]+$ ]]; then
    return 0
  fi
  err "Cloud Run minimum instances must be a non-negative integer or 'default'"
  exit 1
}

validate_traffic_settings() {
  if [[ -n "$TRAFFIC_TAG" && ! "$TRAFFIC_TAG" =~ ^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$ ]]; then
    err "Cloud Run traffic tag must be a lowercase DNS label of at most 63 characters"
    exit 1
  fi
  if [[ "$NO_TRAFFIC" == true && -z "$TRAFFIC_TAG" ]]; then
    err "--no-traffic requires --traffic-tag so the candidate can be health checked"
    exit 1
  fi
}

append_tagged_candidate_host() {
  [[ "$NO_TRAFFIC" == true ]] || return 0

  local service_url service_host candidate_host
  service_url="$(gcloud run services describe "$SERVICE_NAME" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --format='value(status.url)' \
    --quiet)"
  service_host="${service_url#https://}"
  service_host="${service_host%%/*}"
  if [[ -z "$service_host" || ! "$service_host" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]]; then
    err "Could not derive the Cloud Run service host required for tagged candidate health checks"
    exit 1
  fi

  candidate_host="${TRAFFIC_TAG}---${service_host}"
  if [[ ",${ALLOWED_HOSTS}," != *",${candidate_host},"* ]]; then
    ALLOWED_HOSTS="${ALLOWED_HOSTS:+${ALLOWED_HOSTS},}${candidate_host}"
    export ALLOWED_HOSTS
  fi
  log "Added the exact tagged candidate host to ALLOWED_HOSTS for staged health checks"
}

select_config_python_cmd() {
  CONFIG_PYTHON_CMD=(python)

  local is_apple_silicon current_arch
  is_apple_silicon="$(sysctl -n hw.optional.arm64 2>/dev/null || true)"
  [[ "$is_apple_silicon" == "1" ]] || return 0

  current_arch="$(python -c 'import platform; print(platform.machine())' 2>/dev/null || true)"
  [[ "$current_arch" == "x86_64" ]] || return 0

  if command -v arch >/dev/null 2>&1 \
    && arch -arm64 python -c 'import platform; raise SystemExit(0 if platform.machine() == "arm64" else 1)' >/dev/null 2>&1; then
    CONFIG_PYTHON_CMD=(arch -arm64 python)
    log "Detected x86_64 python on Apple Silicon; validating backend settings with native arm64 python"
  fi
}

# コマンドライン引数のパース。
# たとえば `--project-id` や `--region` などを受け取って、内部変数へ格納します。
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID_ARG="$2"
      shift 2
      ;;
    --region)
      REGION_ARG="$2"
      shift 2
      ;;
    --service)
      SERVICE_NAME="$2"
      shift 2
      ;;
    --artifact-repo)
      ARTIFACT_REPOSITORY="$2"
      shift 2
      ;;
    --image-tag)
      IMAGE_TAG="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --run-timeout)
      RUN_TIMEOUT_ARG="$2"
      shift 2
      ;;
    --min-instances)
      MIN_INSTANCES_ARG="$2"
      shift 2
      ;;
    --no-cpu-throttling)
      NO_CPU_THROTTLING=true
      shift 1
      ;;
    --no-traffic)
      NO_TRAFFIC=true
      shift 1
      ;;
    --traffic-tag)
      TRAFFIC_TAG="$2"
      shift 2
      ;;
    --build-arg)
      EXTRA_BUILD_ARGS+=("$2")
      shift 2
      ;;
    --generate-secret)
      GENERATE_SECRET=true
      shift 1
      ;;
    --secret-length)
      SECRET_LENGTH="$2"
      shift 2
      ;;
    --machine-type)
      MACHINE_TYPE="$2"
      shift 2
      ;;
    --timeout)
      BUILD_TIMEOUT="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift 1
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

# どの env ファイルを使うか決める。
# 明示指定がなければ、まず `.env.deploy`、無ければ `.env` を探します。
if [[ -z "$ENV_FILE" ]]; then
  if [[ -f ".env.deploy" ]]; then
    ENV_FILE=".env.deploy"
  elif [[ -f ".env" ]]; then
    ENV_FILE=".env"
  else
    err "Env file not found. Create .env.deploy or specify --env-file."
    exit 1
  fi
fi

if [[ ! "$SECRET_LENGTH" =~ ^[0-9]+$ ]]; then
  err "--secret-length must be numeric"
  exit 1
fi

validate_traffic_settings

if [[ ! -f "$ENV_FILE" ]]; then
  err "Env file does not exist: $ENV_FILE"
  exit 1
fi

# ここで env ファイルを読み込み、以降の処理からは通常の環境変数として扱います。
log "Loading environment variables from $ENV_FILE"
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

PROJECT_ID="${PROJECT_ID_ARG:-${PROJECT_ID:-}}"
REGION="${REGION_ARG:-${REGION:-}}"
if [[ -z "${ENVIRONMENT:-}" ]]; then
  ENVIRONMENT=production
fi
export ENVIRONMENT

# セッション用の秘密鍵が空なら、自動生成する。
# 本番では十分な長さのランダム文字列が必須のため、開発者が入れ忘れても
# `--generate-secret` かこの自動分岐で安全な値が作られます。
if [[ "$GENERATE_SECRET" == true || -z "${SESSION_SECRET_KEY:-}" ]]; then
  if [[ "$GENERATE_SECRET" == false ]]; then
    log "SESSION_SECRET_KEY is missing; enabling --generate-secret automatically"
  fi
  require_cmd openssl
  SESSION_SECRET_KEY="$(openssl rand -base64 "$SECRET_LENGTH" | tr -d '\r\n')"
  export SESSION_SECRET_KEY
  log "Generated SESSION_SECRET_KEY with length $SECRET_LENGTH"
fi

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(get_gcloud_config_value 'project')"
  if [[ -n "$PROJECT_ID" ]]; then
    log "PROJECT_ID not provided; falling back to gcloud config project: $PROJECT_ID"
  fi
fi

if [[ -z "$REGION" ]]; then
  REGION="$(get_gcloud_config_value 'run/region')"
  if [[ -n "$REGION" ]]; then
    log "REGION not provided; falling back to gcloud config run/region: $REGION"
  fi
fi

if [[ -z "$REGION" ]]; then
  REGION="$(get_gcloud_config_value 'compute/region')"
  if [[ -n "$REGION" ]]; then
    log "REGION not provided; falling back to gcloud config compute/region: $REGION"
  fi
fi

if [[ -z "$PROJECT_ID" ]]; then
  err "PROJECT_ID is required (use --project-id, set in env file, or configure gcloud)"
  exit 1
fi

if [[ -z "$REGION" ]]; then
  err "REGION is required (use --region, set in env file, or configure gcloud)"
  exit 1
fi

add_env_key "ENVIRONMENT"
add_env_key "ADMIN_EMAIL_ALLOWLIST"
add_env_key "SESSION_SECRET_KEY"
add_env_key "CORS_ALLOWED_ORIGINS"
add_env_key "TRUSTED_PROXY_IPS"
add_env_key "ALLOWED_HOSTS"
# Cloud Run へ適用する実行パラメータ（任意）
# - CLOUD_RUN_TIMEOUT: 例 360s, 10m
# - CLOUD_RUN_MIN_INSTANCES: 例 0, 1, default
# - CLOUD_RUN_NO_CPU_THROTTLING: true/false

RUN_TIMEOUT="${RUN_TIMEOUT_ARG:-${CLOUD_RUN_TIMEOUT:-}}"
MIN_INSTANCES="${MIN_INSTANCES_ARG:-${CLOUD_RUN_MIN_INSTANCES:-}}"
validate_min_instances "$MIN_INSTANCES"
NO_CPU_THROTTLING="${NO_CPU_THROTTLING:-${CLOUD_RUN_NO_CPU_THROTTLING:-false}}"

while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%%$'\r'}"
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
    add_env_key "${BASH_REMATCH[1]}"
  fi
done < "$ENV_FILE"

for ignore_key in "${IGNORE_DEPLOY_KEYS[@]}"; do
  unset "DEPLOY_ENV_KEYS[$ignore_key]"
done

# ここで「絶対に必要な環境変数」を一覧表示しつつ、値が空でないかをまとめてチェックします。
# どれか1つでも欠けていると Pydantic の検証や gcloud 実行まで進ませずに終了させ、
# 「何が足りないか」を前段で明示して環境差分に気付きやすくします。
log "Pre-flight: ensuring required keys exist before validation: ${REQUIRED_DEPLOY_KEYS[*]}"
for required_key in "${REQUIRED_DEPLOY_KEYS[@]}"; do
  if [[ -z "${!required_key:-}" ]]; then
    err "$required_key must be set in $ENV_FILE or environment (pre-flight check stops before validation)"
    exit 1
  fi
done

# Firestore 接続にはプロジェクト ID が必須。バックエンド config.py と同じエイリアスを許容する。
# 優先順位: FIRESTORE_PROJECT_ID > GCP_PROJECT_ID > GOOGLE_CLOUD_PROJECT > PROJECT_ID
_FIRESTORE_PROJECT="${FIRESTORE_PROJECT_ID:-${GCP_PROJECT_ID:-${GOOGLE_CLOUD_PROJECT:-${PROJECT_ID:-}}}}"
if [[ -z "$_FIRESTORE_PROJECT" ]]; then
  err "Firestore project ID must be set via FIRESTORE_PROJECT_ID, GCP_PROJECT_ID, GOOGLE_CLOUD_PROJECT, or PROJECT_ID in $ENV_FILE or environment"
  exit 1
fi

# ここから先は、デプロイに必要な Git / Python / gcloud を使っていきます。
require_cmd git
IMAGE_TAG="${IMAGE_TAG:-$(git rev-parse --short HEAD)}"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${ARTIFACT_REPOSITORY}:${IMAGE_TAG}"

# Python 側の設定（Pydantic モデル）を一度ロードして、値が正しいかチェックします。
# ここで失敗すれば Cloud Build へ進まないため、「壊れた設定で本番デプロイ」は防げます。
require_cmd python
select_config_python_cmd
log "Validating backend settings via ${CONFIG_PYTHON_CMD[*]} -m apps.backend.backend.config"
PYTHONPATH="$REPO_ROOT" "${CONFIG_PYTHON_CMD[@]}" -m apps.backend.backend.config >/dev/null
log "Backend configuration validated successfully"

# dry-run モードでは Cloud Build / Cloud Run には触らず、
# 「設定読み込み〜バリデーション」までを実行して即終了します。
if [[ "$DRY_RUN" == true ]]; then
  log "Dry run mode: skipping gcloud build/deploy"
  log "Prepared image URI: $IMAGE_URI"
  if [[ -n "$MIN_INSTANCES" ]]; then
    log "Prepared Cloud Run minimum instances: $MIN_INSTANCES"
  fi
  if [[ "$NO_TRAFFIC" == true ]]; then
    log "Prepared Cloud Run traffic mode: tagged candidate without production traffic"
  fi
  exit 0
fi

# Firestore インデックスの同期フェーズ。
# 既に CI などで同期済みの環境では `SKIP_FIRESTORE_INDEX_SYNC=true` を付けて
# スキップすることもできます。
if [[ "${SKIP_FIRESTORE_INDEX_SYNC:-false}" == "true" ]]; then
  log "Skipping Firestore index sync because SKIP_FIRESTORE_INDEX_SYNC=true"
else
  log "Syncing Firestore indexes via Firebase CLI before deployment"
  "${SCRIPT_DIR}/deploy_firestore_indexes.sh" --tool firebase --project "$PROJECT_ID"
fi

ensure_gcloud
append_tagged_candidate_host

# Cloud Build にソースコードを送って Docker イメージをビルドします。
# IMAGE_URI には「リージョン + Artifact Registry + イメージタグ」が入っています。
log "Submitting build to Cloud Build: $IMAGE_URI"
# Cloud Build では repo-root の Dockerfile がアップロード対象から外れてしまうケースがあるため、
# `--tag` による暗黙ビルド（Dockerfile 固定）ではなく、Dockerfile.backend を明示した構成でビルドします。
# これにより "Dockerfile: no such file or directory" の失敗を回避します。
BUILDCONFIG_PATH="${REPO_ROOT}/cloudbuild.backend.yaml"
if [[ ! -f "$BUILDCONFIG_PATH" ]]; then
  err "Cloud Build config not found: $BUILDCONFIG_PATH"
  exit 1
fi

GENERATED_BUILDCONFIG=""
cleanup_generated_buildconfig() {
  [[ -n "$GENERATED_BUILDCONFIG" && -f "$GENERATED_BUILDCONFIG" ]] && rm -f "$GENERATED_BUILDCONFIG"
}
trap cleanup_generated_buildconfig EXIT

SUBSTITUTIONS=("_IMAGE_URI=${IMAGE_URI}")
CONFIG_TO_USE="$BUILDCONFIG_PATH"

if [[ ${#EXTRA_BUILD_ARGS[@]} -gt 0 ]]; then
  # --build-arg を指定された場合は Cloud Build config を一時生成して docker build args に反映します。
  GENERATED_BUILDCONFIG="$(mktemp "${REPO_ROOT}/.cloudbuild.backend.XXXXXX.yaml")"
  {
    echo "steps:"
    echo "  - name: gcr.io/cloud-builders/docker"
    echo "    args:"
    echo "      - build"
    echo "      - -f"
    echo "      - Dockerfile.backend"
    echo "      - -t"
    echo "      - \$_IMAGE_URI"
    for build_arg in "${EXTRA_BUILD_ARGS[@]}"; do
      echo "      - --build-arg"
      echo "      - ${build_arg}"
    done
    echo "      - ."
    echo ""
    echo "images:"
    echo "  - \$_IMAGE_URI"
  } >"$GENERATED_BUILDCONFIG"
  CONFIG_TO_USE="$GENERATED_BUILDCONFIG"
fi

BUILD_CMD=(
  gcloud builds submit
  --project "$PROJECT_ID"
  --config "$CONFIG_TO_USE"
  --substitutions "$(IFS=,; echo "${SUBSTITUTIONS[*]}")"
  --machine-type "$MACHINE_TYPE"
  --timeout "$BUILD_TIMEOUT"
)
"${BUILD_CMD[@]}"

log "Preparing environment variable file for Cloud Run"
# Cloud Run の `--set-env-vars` はカンマ区切りで扱いが難しいため、
# 一旦 YAML 形式の一時ファイルを作り、`--env-vars-file` でまとめて適用します。
# mktemp で生成した一時ファイルは trap により必ず削除し、秘密情報が
# リポジトリやディスク上に残らないようにします。
ENV_VARS_FILE="$(mktemp "${REPO_ROOT}/.cloudrun.env.XXXXXX")"
cleanup_env_file() {
  [[ -f "$ENV_VARS_FILE" ]] && rm -f "$ENV_VARS_FILE"
}
trap cleanup_env_file EXIT

mapfile -t SORTED_DEPLOY_KEYS < <(printf '%s\n' "${!DEPLOY_ENV_KEYS[@]}" | sort)
{
  for key in "${SORTED_DEPLOY_KEYS[@]}"; do
    value="${!key-}"
    [[ -z "$value" ]] && continue
    escaped="$(escape_yaml_value "$value")"
    printf '%s: "%s"\n' "$key" "$escaped"
  done
} >"$ENV_VARS_FILE"

if [[ ! -s "$ENV_VARS_FILE" ]]; then
  err "No environment variables collected for deployment"
  exit 1
fi

log "Deploying service ${SERVICE_NAME} to region ${REGION} with env file ${ENV_VARS_FILE}"
RUN_ARGS=()
if [[ -n "${RUN_TIMEOUT:-}" ]]; then
  RUN_ARGS+=(--timeout "$RUN_TIMEOUT")
fi
if [[ -n "${MIN_INSTANCES:-}" ]]; then
  RUN_ARGS+=(--min "$MIN_INSTANCES")
fi
if [[ "${NO_CPU_THROTTLING}" == "true" ]]; then
  RUN_ARGS+=(--no-cpu-throttling)
fi
if [[ "$NO_TRAFFIC" == true ]]; then
  RUN_ARGS+=(--no-traffic)
fi
if [[ -n "$TRAFFIC_TAG" ]]; then
  RUN_ARGS+=(--tag "$TRAFFIC_TAG")
fi

gcloud run deploy "$SERVICE_NAME" \
  --project "$PROJECT_ID" \
  --image "$IMAGE_URI" \
  --region "$REGION" \
  --allow-unauthenticated \
  --env-vars-file "$ENV_VARS_FILE" \
  "${RUN_ARGS[@]}"

log "Deployment completed"
