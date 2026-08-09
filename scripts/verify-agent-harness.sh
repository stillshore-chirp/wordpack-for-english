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

COMMON_FILES=(
  "AGENTS.md"
  "CLAUDE.md"
  "docs/agent-harness.md"
  "docs/agent-principles.md"
  "apps/frontend/AGENTS.md"
  "apps/backend/AGENTS.md"
  "docs/operations/AGENTS.md"
  "requirements-agent-harness.txt"
  "scripts/validate_agent_frontmatter.py"
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
done
for file in "${CLAUDE_RULES[@]}" "${CLAUDE_SKILLS[@]}" "${CURSOR_RULES[@]}"; do
  max_size "$file" 30 4096
done

python3 scripts/validate_agent_frontmatter.py --self-test
python3 scripts/validate_agent_frontmatter.py \
  "${CANONICAL_SKILLS[@]}" \
  "${CLAUDE_RULES[@]}" \
  "${CLAUDE_SKILLS[@]}" \
  "${CURSOR_RULES[@]}"

CLAUDE_CONTENT="$(tr -d '\r' < CLAUDE.md | sed '/^[[:space:]]*$/d')"
[[ "$CLAUDE_CONTENT" == "@AGENTS.md" ]] || fail "CLAUDE.md must contain only @AGENTS.md"

for file in "${CLAUDE_RULES[@]}"; do
  require_text "$file" "AGENTS.md"
done
for file in "${CLAUDE_SKILLS[@]}"; do
  require_text "$file" ".agents/skills/"
  require_text "$file" "唯一の手順正本"
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
  "docs/api-reference.md" \
  "docs/authentication.md" \
  "docs/firestore.md" \
  ".github/workflows/**"; do
  require_text "AGENTS.md" "$path"
done

reject_text "AGENTS.md" "コードレビュー往復は最大 10 回"
reject_text "AGENTS.md" "P0 または P1 を含まないレビュー結果が 3 回連続"
reject_text "AGENTS.md" "codex/<目的>"
reject_text "AGENTS.md" "Codex 自動コードレビュー"
reject_text "AGENTS.md" "リポジトリ変更の公開まで依頼されている場合"
reject_text ".agents/skills/github-delivery/SKILL.md" "ユーザーが完成した変更のPRを求めている場合"
reject_text ".agents/skills/github-delivery/SKILL.md" "typoや同一PR内の局所修正"
reject_text "scripts/verify-ai-governance.sh" ".cursor directory must not be created"
reject_text "scripts/verify-ai-governance.sh" "コードレビュー往復は最大 10 回"
reject_text "scripts/verify-ai-governance.sh" "P0 または P1 を含まないレビュー結果が 3 回連続"

require_text "docs/agent-harness.md" "Hard gateとheuristic"
require_text "docs/agent-harness.md" "Instruction budget"
require_text "docs/agent-harness.md" "clean review"
require_text "docs/agent-principles.md" "重複回数だけで抽象化を強制しない"
require_text "AGENTS.md" "大小を問わずすべてソースコード変更"
require_text "AGENTS.md" "主Issueの検索・作成・更新"
require_text "AGENTS.md" "対象branchで定義されたpush / pull_request等のCI成功"
require_text "AGENTS.md" "GitHub上のmergeabilityがclean"
require_text "AGENTS.md" "自己レビューだけで代替してマージ可能とは報告しません"
require_text ".agents/skills/github-delivery/SKILL.md" "大小を問わず必ず発動"
require_text ".agents/skills/github-delivery/SKILL.md" "ソースコード変更は規模や種類にかかわらず主Issueを必須"
require_text ".agents/skills/github-delivery/SKILL.md" "非ドラフトPRを作成または更新"
require_text ".agents/skills/github-delivery/SKILL.md" "GitHubのmergeabilityがclean"
require_text "docs/agent-harness.md" "ソースコード変更のGitHub配送権限"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "自己レビューは補助証跡に限り"
require_text ".github/pull_request_template.md" "push CI"
require_text ".github/pull_request_template.md" "pull_request CI"
require_text ".github/pull_request_template.md" "GitHub mergeability"

echo "Agent harness verification: PASS"
