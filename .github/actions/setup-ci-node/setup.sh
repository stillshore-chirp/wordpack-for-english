#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Refresh this version and hash together from the official release manifest:
# https://nodejs.org/dist/v22.23.4/SHASUMS256.txt
readonly NODE_VERSION="22.23.4"
readonly NODE_ARCHIVE_SHA256="1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce"
readonly NODE_ARCHIVE="node-v${NODE_VERSION}-linux-x64.tar.xz"
readonly NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_ARCHIVE}"
readonly EXPECTED_NODE_VERSION="v${NODE_VERSION}"

fail() {
  printf 'setup-ci-node: %s\n' "$1" >&2
  exit 1
}

has_line_break() {
  [[ "$1" == *$'\n'* || "$1" == *$'\r'* ]]
}

runner_temp="${RUNNER_TEMP:-}"
github_path="${GITHUB_PATH:-}"
if [[ -z "$runner_temp" || "$runner_temp" != /* || ! -d "$runner_temp" || ! -w "$runner_temp" ]] || has_line_break "$runner_temp"; then
  fail 'RUNNER_TEMP must be an absolute writable directory without line breaks.'
fi
if [[ -z "$github_path" || -d "$github_path" ]] || has_line_break "$github_path"; then
  fail 'GITHUB_PATH must be a file path without line breaks.'
fi

os="$(uname -s)"
arch="$(uname -m)"
if [[ "$os" != 'Linux' || "$arch" != 'x86_64' ]]; then
  fail "Unsupported runner platform: ${os}/${arch}; this action supports Linux x86_64 only."
fi

node_binary=''
tool_cache="${RUNNER_TOOL_CACHE:-}"
if [[ -n "$tool_cache" && "$tool_cache" == /* ]] && ! has_line_break "$tool_cache"; then
  cached_node="${tool_cache%/}/node/${NODE_VERSION}/x64/bin/node"
  if [[ -x "$cached_node" ]]; then
    if cached_version="$("$cached_node" --version 2>/dev/null)" && [[ "$cached_version" == "$EXPECTED_NODE_VERSION" ]]; then
      node_binary="$cached_node"
    fi
  fi
fi

work_dir=''
keep_work_dir=false
cleanup() {
  local status=$?
  if [[ -n "$work_dir" && "$keep_work_dir" != true ]]; then
    rm -rf -- "$work_dir"
  fi
  return "$status"
}
trap cleanup EXIT

if [[ -z "$node_binary" ]]; then
  work_dir="$(mktemp -d "${runner_temp%/}/ci-node-${NODE_VERSION}.XXXXXX")"
  install_dir="${work_dir}/node"
  archive_path="${work_dir}/${NODE_ARCHIVE}"
  mkdir -p "$install_dir"

  curl \
    --fail \
    --silent \
    --show-error \
    --location \
    --proto '=https' \
    --proto-redir '=https' \
    --tlsv1.2 \
    --connect-timeout 10 \
    --max-time 120 \
    --retry 3 \
    --retry-delay 1 \
    --retry-max-time 45 \
    --output "$archive_path" \
    "$NODE_URL"

  if ! printf '%s  %s\n' "$NODE_ARCHIVE_SHA256" "$archive_path" | sha256sum --check --status; then
    fail 'Downloaded Node.js archive failed SHA-256 verification.'
  fi

  tar --extract --xz --file "$archive_path" --directory "$install_dir" --strip-components=1 --no-same-owner
  rm -f -- "$archive_path"
  node_binary="${install_dir}/bin/node"
fi

if [[ ! -x "$node_binary" ]]; then
  fail 'Selected Node.js binary is missing or not executable.'
fi
if actual_version="$("$node_binary" --version 2>/dev/null)" && [[ "$actual_version" == "$EXPECTED_NODE_VERSION" ]]; then
  :
else
  fail "Selected Node.js binary did not report ${EXPECTED_NODE_VERSION}."
fi

node_bin_dir="${node_binary%/node}"
if [[ "$node_bin_dir" == "$node_binary" || "$node_bin_dir" != /* ]] || has_line_break "$node_bin_dir"; then
  fail 'Selected Node.js binary path is invalid.'
fi

: >> "$github_path"
printf '%s\n' "$node_bin_dir" >> "$github_path"
if [[ -n "$work_dir" ]]; then
  keep_work_dir=true
fi
printf 'setup-ci-node: Node.js %s ready.\n' "$NODE_VERSION"
