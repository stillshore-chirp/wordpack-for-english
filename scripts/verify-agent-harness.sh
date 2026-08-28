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
if any(
    token.type == "heading_open" and token.level == 0 and token.tag in {"h1", "h2"}
    for token in tokens[start_index + 1 : end_index]
):
    raise SystemExit(2)
if end_index + 1 < len(tokens):
    next_token = tokens[end_index + 1]
    if not (
        next_token.type == "heading_open"
        and next_token.level == 0
        and next_token.tag in {"h1", "h2"}
    ):
        raise SystemExit(2)

visible_lines: list[str] = []
for token in tokens[start_index + 1 : end_index]:
    if token.type == "html_block":
        raise SystemExit(2)
    if token.type != "inline":
        continue
    inline_text: list[str] = []
    for child in token.children or []:
        if child.type in {"text", "code_inline"}:
            inline_text.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            inline_text.append("\n")
        elif child.type == "image":
            inline_text.append(f" {child.content} ")
        elif child.type == "html_inline":
            raise SystemExit(2)
        elif child.content:
            inline_text.append(f" {child.content} ")
    visible_lines.append("".join(inline_text))

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
require_block_text \
  <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required **invariant**' '<!-- agent-harness:self-test:end -->') \
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
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<div hidden>' '' 'required invariant' '' '</div>' '' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside a hidden HTML container"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '<span hidden>required invariant</span>' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted required text inside inline HTML"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required' 'invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification joined required text across a soft break"
fi
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' 'required![other content](missing.png)invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification dropped image content inside required text"
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
if (
  require_block_text \
    <(printf '%s\n' '## Checked' '<!-- agent-harness:self-test:start -->' '# Replacement' 'required invariant' '<!-- agent-harness:self-test:end -->') \
    "## Checked" \
    "self-test" \
    "required invariant"
) >/dev/null 2>&1; then
  fail "block verification accepted a canonical block spanning a peer heading"
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
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "配送対象の最終HEADではfull gateを原則1回実行します"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "包括レビューは同一PR・同一HEAD系列で原則2周まで"
require_block_text "AGENTS.md" "## 作業の進め方" "workflow" "P2以下だけなら影響とnon-blocking判断を記録して収束"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "UI変更レビュー: 変更した画面、component、状態、文言、操作を確認する。単一画面の局所変更だけならフロー監査を追加しない。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "フロー監査: 既存画面または複数ステップの体験を監査する依頼、または画面遷移を追わなければタスク達成を評価できない場合に使う。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "併用: UI変更が複数ステップの主要タスクへ影響する場合、取得可能な変更前フローを基準にし、変更レビュー後に同じタスクの変更後フローを監査する。片方の証跡で他方を代用しない。"
require_block_text ".agents/skills/ui-ux-review/SKILL.md" "## 2. レビュー経路を選ぶ" "uiux-review-routing" "GitHubが所有する未変更の操作フローを監査対象へ広げず"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "同一PR・同一HEAD系列の包括レビューは、配送対象の最終HEADに対する初回レビュー1回と、指摘修正後の再レビュー1回までを原則とする"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "同じ配送系列への包括レビュー実行回数で数え、review comment、thread、指摘の件数では数えない"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "3回目以降の包括レビューは実行しません。次のいずれかで前回証拠が失効した場合だけ、対象risk laneと変更pathを明示した限定再確認を行う"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "未解決のP0またはP1"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "セキュリティ、秘密情報、データ整合性に関わる未解決事項"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "前回レビュー後に新しい変更範囲またはrisk laneが追加された"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "前回のレビュー証拠に具体的な不足または矛盾が見つかった"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "P2以下の指摘だけが残る場合は、影響とnon-blocking判断をPRへ記録し、必要なら別Issueへ分離して同じPRの包括レビュー周回を終了する"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "修正commit、変更path、元の指摘、focused test結果だけを文脈として使う"
require_block_text "docs/agent-harness.md" "## GitHub reviewの収束" "review-convergence" "成功済みレビューまたはfull gateを再実行する場合は、対象変更、新規risk lane、実行条件変更、証拠期限切れなど、証拠が失効した具体的な理由を記録する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "対象HEAD、対象path、確認する具体的な問い"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "既存報告やメインエージェント自身の一次証拠確認では不足する理由"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "同一HEAD・同一risk laneの独立監査は原則1回"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "包括監査を複数agentへ同時委任せず"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "再監査を認めるのは、対象コードが変わった、新しい実行証拠が得られた、前回監査に明確な不足がある、または未解決の証拠矛盾がある場合"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "修正後に変更pathを対象再検証すること"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "監査結果が矛盾した場合は追加agentの多数決を取りません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "full-history forkを既定にしません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "必要なHEAD、path、acceptance、既知の指摘だけを短く渡します"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "開発中は変更によって影響を受けるfocused test"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "配送対象の最終HEADが確定した時点でfrontend / backend / operationsなど必要なfull gateを原則1回実行する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "成功済み検証を再実行する時は、対象変更、生成物変更、実行条件変更、証拠期限切れなど、証拠が失効した理由を記録する"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "HEADだけを監査済みsnapshotとして扱いません"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| verified snapshot |"
require_block_text "docs/agent-harness.md" "## Subagent orchestration" "subagent-orchestration" "| invalidation condition |"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "docs/agent-harness.md"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## サブエージェント運用" "subagent-maintenance" "同一HEADの重複監査"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## Review収束" "review-maintenance" "docs/agent-harness.md"
require_block_text "docs/ai-governance/13-maintenance-policy.md" "## Review収束" "review-maintenance" "P2以下だけを理由とする包括レビュー反復"
require_text ".agents/skills/github-delivery/SKILL.md" "docs/agent-harness.md"
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
