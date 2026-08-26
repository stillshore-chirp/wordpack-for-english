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

require_block_text() {
  local file="$1"
  local heading="$2"
  local block="$3"
  local pattern="$4"
  local start="<!-- agent-harness:${block}:start -->"
  local end="<!-- agent-harness:${block}:end -->"
  local content
  content="$(python3 - "$file" "$heading" "$start" "$end" <<'PY'
import sys

from markdown_it import MarkdownIt

path, heading, start, end = sys.argv[1:]
source = open(path, encoding="utf-8").read()
tokens = MarkdownIt("commonmark").parse(source)

headings = [
    index
    for index, token in enumerate(tokens[:-2])
    if token.type == "heading_open"
    and token.tag == "h2"
    and token.level == 0
    and tokens[index + 1].type == "inline"
    and tokens[index + 1].content == heading.removeprefix("## ")
    and tokens[index + 2].type == "heading_close"
]
starts = [
    index
    for index, token in enumerate(tokens)
    if token.type == "html_block" and token.level == 0 and token.content.strip() == start
]
ends = [
    index
    for index, token in enumerate(tokens)
    if token.type == "html_block" and token.level == 0 and token.content.strip() == end
]
if len(headings) != 1 or len(starts) != 1 or len(ends) != 1:
    raise SystemExit(2)
heading_index = headings[0]
start_index = starts[0]
end_index = ends[0]
heading_map = tokens[heading_index].map
start_map = tokens[start_index].map
if (
    heading_map is None
    or start_map is None
    or start_map[0] != heading_map[1]
    or start_index <= heading_index + 2
    or end_index <= start_index
):
    raise SystemExit(2)

visible_lines: list[str] = []
for token in tokens[start_index + 1 : end_index]:
    if token.type != "inline":
        continue
    for child in token.children or []:
        if child.type in {"text", "code_inline"}:
            visible_lines.append(child.content)

print("\n".join(visible_lines))
PY
)" || fail "$file block $block must immediately follow heading: $heading"
  grep -Fq -- "$pattern" <<< "$content" || fail "$file block $block must contain: $pattern"
}

require_block_text \
  <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '> ````md' '> <!-- literal in fenced code -->' '> # Replacement' '> ## Example' '> ````' 'required invariant' '<!-- agent-harness:self-test:end -->') \
  "## Checked" \
  "self-test" \
  "required invariant"
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '> ```md' '> required invariant' '> ```' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside fenced code"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<!-- required invariant -->' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside an HTML comment"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<!-- agent-harness:self-test:end -->' 'required invariant') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text outside its canonical block"
fi
if (
  require_block_text \
    <(printf '%s\n' '<!--' '## Checked' '<!-- agent-harness:self-test:start -->' 'required invariant' '<!-- agent-harness:self-test:end -->' '-->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block inside an HTML comment"
fi
if (
  require_block_text \
    <(printf '%s\n' '````md' '## Checked' '<!-- agent-harness:self-test:start -->' 'required invariant' '<!-- agent-harness:self-test:end -->' '````') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block inside fenced code"
fi

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
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "サブエージェントは独立したrisk laneへ積極的に使います"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "docs/agent-harness.md"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "対象HEAD、対象path、確認する具体的な問い"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "既存報告やメインエージェント自身の一次証拠確認では不足する理由"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "同一HEAD・同一risk laneの独立監査は原則1回"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "監査結果が矛盾した場合は追加agentの多数決を取りません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "full-history forkを既定にしません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "開発中は変更によって影響を受けるfocused test"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "HEADだけを監査済みsnapshotとして扱いません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| verified snapshot |"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| invalidation condition |"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "docs/agent-harness.md"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "同一HEADの重複監査"
require_text "docs/agent-principles.md" "重複回数だけで抽象化を強制しない"
require_text "AGENTS.md" "大小を問わずすべてソースコード変更"
require_text "AGENTS.md" "GitHub配送Skillが定義する通常配送"
require_text "AGENTS.md" "GitHub上でCIとコードレビュー対応が完了し、マージ可能な状態"
require_text "AGENTS.md" "観測可能な完了条件"
require_text "AGENTS.md" "独立した責務を未commitのまま蓄積せず"
require_text "AGENTS.md" "GitHub配送Skillを正本"
require_text ".agents/skills/github-delivery/SKILL.md" "大小を問わず必ず発動"
require_text ".agents/skills/github-delivery/SKILL.md" "ソースコード変更は規模や種類にかかわらず主Issueを必須"
require_text ".agents/skills/github-delivery/SKILL.md" "非ドラフトPRを作成または更新"
require_text ".agents/skills/github-delivery/SKILL.md" "GitHubのmergeabilityがclean"
require_text ".agents/skills/github-delivery/SKILL.md" "予定commitの責務"
require_text ".agents/skills/github-delivery/SKILL.md" "次の独立責務を編集する前"
require_text ".agents/skills/github-delivery/SKILL.md" "サブエージェントの完了報告を受けたら"
require_text ".agents/skills/github-delivery/SKILL.md" "作業時間、行数、担当者だけを理由"
require_text ".agents/skills/github-delivery/SKILL.md" "git diff --cached --check"
require_text "docs/agent-harness.md" "ソースコード変更のGitHub配送権限"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "自己レビューは補助証跡に限り"
require_text ".github/pull_request_template.md" "push CI"
require_text ".github/pull_request_template.md" "pull_request CI"
require_text ".github/pull_request_template.md" "GitHub mergeability"

echo "Agent harness verification: PASS"
