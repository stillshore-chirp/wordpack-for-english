#!/usr/bin/env bash
set -euo pipefail

# Firestore エミュレータを firebase-tools で起動し、firebase.json / firestore.indexes.json を自動読み込みする。
# 既存の firebase-tools がなければ npx 経由で取得し、--import/--export-on-exit でデータも永続化する。

SCRIPT_NAME=$(basename "$0")
PROJECT_ID=${FIRESTORE_PROJECT_ID:-wordpack-local}
EMULATOR_PORT=${FIRESTORE_EMULATOR_PORT:-8080}
BIND_ADDR="127.0.0.1"
IMPORT_DIR=${FIRESTORE_EMULATOR_DATA:-firestore-emulator-data}
TEMP_CONFIG=""

print_usage() {
  cat <<'USAGE'
Usage: scripts/start_firestore_emulator.sh [--project-id <id>] [--port <port>] [--bind <addr>] [--import-dir <path>]

Options:
  --project-id   Firestore/Firebase プロジェクト ID（エミュレータでも必須、既定: wordpack-local）
  --port         エミュレータの公開ポート（既定: 8080）
  --bind         バインド先アドレス（既定: 127.0.0.1。Docker で公開したい場合は 0.0.0.0）
  --import-dir   --import/--export-on-exit に使うディレクトリ（既定: firestore-emulator-data）
  --help         このヘルプを表示
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-id)
      PROJECT_ID="$2"
      shift 2
      ;;
    --port)
      EMULATOR_PORT="$2"
      shift 2
      ;;
    --bind)
      BIND_ADDR="$2"
      shift 2
      ;;
    --import-dir)
      IMPORT_DIR="$2"
      shift 2
      ;;
    --help|-h)
      print_usage
      exit 0
      ;;
    *)
      echo "[${SCRIPT_NAME}] Unknown option: $1" >&2
      print_usage >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "firebase.json" ]]; then
  echo "[${SCRIPT_NAME}] firebase.json が見つかりません。リポジトリルートで実行してください。" >&2
  exit 1
fi
if [[ ! -f "firestore.indexes.json" ]]; then
  echo "[${SCRIPT_NAME}] firestore.indexes.json が見つかりません。" >&2
  exit 1
fi

mkdir -p "$IMPORT_DIR"

# firebase-tools の Firestore エミュレータは Java 21 以上が必須。
# node:bookworm ベースには入っていないため、未満の場合は Adoptium の Temurin 21 を追加インストールする。
ensure_java21() {
  if command -v java >/dev/null 2>&1 && java -version 2>&1 | grep -q 'version "21'; then
    return 0
  fi

  local os_name
  os_name="$(uname -s)"
  if [[ "$os_name" != "Linux" ]]; then
    echo "[${SCRIPT_NAME}] Java 21+ が必要です。${os_name} では自動インストールできないため、手動で導入してください。" >&2
    echo "[${SCRIPT_NAME}] macOS の例: brew install openjdk@21 && export PATH=\"/opt/homebrew/opt/openjdk@21/bin:\$PATH\"" >&2
    exit 1
  fi

  echo "[${SCRIPT_NAME}] Java 21+ is required. Installing Temurin 21 (Adoptium tarball, no apt)..."
  # 過去の失敗で残った外部 repo 設定を掃除（念のため）
  rm -f /etc/apt/sources.list.d/adoptium.list /usr/share/keyrings/adoptium.gpg || true

  apt-get update -y
  apt-get install -y --no-install-recommends ca-certificates curl tar
  update-ca-certificates || true

  TMP_TAR=$(mktemp /tmp/temurin21.XXXX.tgz)
  if ! curl -fsSL --retry 3 --retry-delay 2 \
    "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse" \
    -o "$TMP_TAR"; then
    echo "[${SCRIPT_NAME}] Failed to download Java 21 JRE (api.adoptium.net). Please ensure HTTPS connectivity or preinstall Java 21 in the image." >&2
    exit 1
  fi

  mkdir -p /opt/temurin-21-jre
  tar -xzf "$TMP_TAR" -C /opt/temurin-21-jre --strip-components=1
  ln -sf /opt/temurin-21-jre/bin/java /usr/local/bin/java
  rm -f "$TMP_TAR"

  java -version
}

ensure_java21

export FIRESTORE_EMULATOR_HOST="${BIND_ADDR}:${EMULATOR_PORT}"
echo "[${SCRIPT_NAME}] FIRESTORE_EMULATOR_HOST=${FIRESTORE_EMULATOR_HOST}"
echo "[${SCRIPT_NAME}] firebase.json / firestore.indexes.json を読み込み、Firestore エミュレータを起動します。"
echo "[${SCRIPT_NAME}] データは '${IMPORT_DIR}' に --import/--export-on-exit で永続化されます。"

# firebase-tools は emulators:start に --host/--port を直接渡すとエラーになる場合があるため、
# 一時的な firebase.json を生成して host/port を上書きする。
TEMP_CONFIG="$(mktemp /tmp/firebase.emulator.XXXX.json)" || {
  echo "[${SCRIPT_NAME}] failed to create temp config" >&2
  exit 1
}
export TEMP_CONFIG
export EMULATOR_BIND="${BIND_ADDR}"
export EMULATOR_PORT_VALUE="${EMULATOR_PORT}"
node - <<'EOF'
const fs = require('fs');
const path = require('path');

const basePath = path.resolve('firebase.json');
const outPath = process.env.TEMP_CONFIG;
const bind = process.env.EMULATOR_BIND || '0.0.0.0';
const port = Number(process.env.EMULATOR_PORT_VALUE || '8080');

if (!fs.existsSync(basePath)) {
  console.error(`[start_firestore_emulator] firebase.json not found at ${basePath}`);
  process.exit(1);
}

const json = JSON.parse(fs.readFileSync(basePath, 'utf8'));
json.emulators = json.emulators || {};
json.emulators.firestore = json.emulators.firestore || {};
json.emulators.firestore.host = bind;
json.emulators.firestore.port = port;

fs.writeFileSync(outPath, JSON.stringify(json, null, 2));
console.log(`[start_firestore_emulator] generated config -> ${outPath}`);
EOF

cleanup() {
  [[ -n "${TEMP_CONFIG}" && -f "${TEMP_CONFIG}" ]] && rm -f "${TEMP_CONFIG}"
}
trap cleanup EXIT

cmd=(
  npx
  -y
  firebase-tools
  emulators:start
  --only
  firestore
  --project
  "$PROJECT_ID"
  --import
  "$IMPORT_DIR"
  --export-on-exit
  --config
  "$TEMP_CONFIG"
)

exec "${cmd[@]}"
