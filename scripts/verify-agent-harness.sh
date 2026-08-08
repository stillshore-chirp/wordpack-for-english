#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

require_file() {
  [[ -f "$1" ]] || fail "required file missing: $1"
}

max_size() {
  local file="$1"
  local max_lines="$2"
  local max_bytes="$3"
  local lines bytes
  lines="$(wc -l < "$file" | tr -d ' ')"
  bytes="$(wc -c < "$file" | tr -d ' ')"
  (( lines <= max_lines )) || fail "$file exceeds ${max_lines} lines: $lines"
  (( bytes <= max_bytes )) || fail "$file exceeds ${max_bytes} bytes: $bytes"
}

require_text() {
  local file="$1"
  local pattern="$2"
  grep -Fq -- "$pattern" "$file" || fail "$file must contain: $pattern"
}

reject_text() {
  local file="$1"
  local pattern="$2"
  if grep -Fq -- "$pattern" "$file"; then
    fail "$file contains retired instruction: $pattern"
  fi
}

validate_skill_frontmatter() {
  local file="$1"
  python3 - "$file" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {path}: {message}")


if not lines or lines[0].strip() != "---":
    fail("frontmatter must start on the first line")

try:
    end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
except StopIteration:
    fail("frontmatter closing delimiter is missing")

fields: dict[str, str] = {}
for line_number, line in enumerate(lines[1:end], start=2):
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    if line[:1].isspace():
        fail(f"nested frontmatter is not supported at line {line_number}")

    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_-]*):[ \t]*(.*)", line)
    if match is None:
        fail(f"invalid frontmatter entry at line {line_number}")

    key, raw_value = match.groups()
    if key in fields:
        fail(f"duplicate frontmatter key: {key}")

    raw_value = raw_value.strip()
    if not raw_value:
        fail(f"frontmatter value must be a string: {key}")

    if raw_value.startswith('"'):
        try:
            value = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            fail(f"invalid quoted string for {key}: {exc.msg}")
    elif raw_value.startswith("'"):
        if len(raw_value) < 2 or not raw_value.endswith("'"):
            fail(f"invalid single-quoted string for {key}")
        value = raw_value[1:-1].replace("''", "'")
    else:
        if raw_value[0] in "[{&*!|>@`" or raw_value.startswith(("- ", "? ", ": ")):
            fail(f"frontmatter value must be a string: {key}")
        lowered = raw_value.lower()
        if lowered in {"null", "~", "true", "false", "yes", "no", "on", "off"}:
            fail(f"frontmatter value must be a string: {key}")
        if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", raw_value):
            fail(f"frontmatter value must be a string: {key}")
        value = raw_value

    if not isinstance(value, str):
        fail(f"frontmatter value must be a string: {key}")
    fields[key] = value

for required in ("name", "description"):
    if required not in fields:
        fail(f"required frontmatter key is missing: {required}")

if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fields["name"]) is None:
    fail("name must be a lowercase kebab-case string")
if not fields["description"].strip():
    fail("description must not be empty")
PY
}

COMMON_FILES=(
  "AGENTS.md"
  "CLAUDE.md"
  "docs/agent-harness.md"
  "docs/agent-principles.md"
  "apps/frontend/AGENTS.md"
  "apps/backend/AGENTS.md"
  "docs/operations/AGENTS.md"
)

CANONICAL_SKILLS=(
  ".agents/skills/ui-ux-review/SKILL.md"
  ".agents/skills/github-delivery/SKILL.md"
  ".agents/skills/production-investigation/SKILL.md"
  ".agents/skills/security-publication/SKILL.md"
)

CLAUDE_RULES=(
  ".claude/rules/frontend.md"
  ".claude/rules/backend.md"
  ".claude/rules/operations.md"
  ".claude/rules/agent-harness.md"
)

CLAUDE_SKILLS=(
  ".claude/skills/ui-ux-review/SKILL.md"
  ".claude/skills/github-delivery/SKILL.md"
  ".claude/skills/production-investigation/SKILL.md"
  ".claude/skills/security-publication/SKILL.md"
)

CURSOR_RULES=(
  ".cursor/rules/frontend.mdc"
  ".cursor/rules/backend.mdc"
  ".cursor/rules/operations.mdc"
  ".cursor/rules/agent-harness.mdc"
)

for file in "${COMMON_FILES[@]}" "${CANONICAL_SKILLS[@]}" "${CLAUDE_RULES[@]}" "${CLAUDE_SKILLS[@]}" "${CURSOR_RULES[@]}"; do
  require_file "$file"
done

max_size "AGENTS.md" 180 16384
for file in "apps/frontend/AGENTS.md" "apps/backend/AGENTS.md" "docs/operations/AGENTS.md"; do
  max_size "$file" 100 8192
  combined_bytes="$(( $(wc -c < AGENTS.md) + $(wc -c < "$file") ))"
  (( combined_bytes <= 24576 )) || fail "AGENTS.md + $file exceeds 24576 bytes: $combined_bytes"
done

for file in "${CANONICAL_SKILLS[@]}"; do
  max_size "$file" 180 16384
  validate_skill_frontmatter "$file"
done

for file in "${CLAUDE_RULES[@]}" "${CLAUDE_SKILLS[@]}" "${CURSOR_RULES[@]}"; do
  max_size "$file" 30 4096
done

for file in "${CLAUDE_SKILLS[@]}"; do
  validate_skill_frontmatter "$file"
done

CLAUDE_CONTENT="$(tr -d '\r' < CLAUDE.md | sed '/^[[:space:]]*$/d')"
[[ "$CLAUDE_CONTENT" == "@AGENTS.md" ]] || fail "CLAUDE.md must contain only @AGENTS.md"

for file in "${CLAUDE_RULES[@]}"; do
  require_text "$file" "paths:"
  require_text "$file" "AGENTS.md"
done

for file in "${CLAUDE_SKILLS[@]}"; do
  require_text "$file" ".agents/skills/"
  require_text "$file" "唯一の手順正本"
done

for file in "${CURSOR_RULES[@]}"; do
  require_text "$file" "description:"
  require_text "$file" "globs:"
  require_text "$file" "alwaysApply: false"
done

for product in "Codex" "Claude Code" "Cursor"; do
  require_text "AGENTS.md" "$product"
  require_text "docs/agent-harness.md" "$product"
  require_text "docs/ai-governance/13-maintenance-policy.md" "$product"
done

for path in \
  ".agents/skills/ui-ux-review/SKILL.md" \
  ".agents/skills/github-delivery/SKILL.md" \
  ".agents/skills/production-investigation/SKILL.md" \
  ".agents/skills/security-publication/SKILL.md" \
  "docs/agent-harness.md" \
  "tests/e2e/**" \
  "tests/**/*.py" \
  ".github/workflows/**"; do
  require_text "AGENTS.md" "$path"
done

reject_text "AGENTS.md" "コードレビュー往復は最大 10 回"
reject_text "AGENTS.md" "P0 または P1 を含まないレビュー結果が 3 回連続"
reject_text "AGENTS.md" "codex/<目的>"
reject_text "AGENTS.md" "Codex 自動コードレビュー"
reject_text "scripts/verify-ai-governance.sh" ".cursor directory must not be created"
reject_text "scripts/verify-ai-governance.sh" "コードレビュー往復は最大 10 回"
reject_text "scripts/verify-ai-governance.sh" "P0 または P1 を含まないレビュー結果が 3 回連続"

require_text "docs/agent-harness.md" "Hard gateとheuristic"
require_text "docs/agent-harness.md" "Instruction budget"
require_text "docs/agent-harness.md" "変更のないheadで追加のclean reviewを複数回集めない"
require_text "docs/agent-principles.md" "重複回数だけで抽象化を強制しない"

echo "Agent harness verification: PASS"
