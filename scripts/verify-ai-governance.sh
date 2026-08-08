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

require_file "AGENTS.md"
require_file "CLAUDE.md"
require_file ".agents/skills/ui-ux-review/SKILL.md"
require_file "docs/ai-governance/00-index.md"
require_file "docs/ai-governance/glossary.md"
require_file "docs/ai-governance/01-agent-operating-contract.md"
require_file "docs/ai-governance/02-uiux-review-framework.md"
require_file "docs/ai-governance/03-evidence-and-completion-gates.md"
require_file "docs/ai-governance/04-cognitive-psychology-principles.md"
require_file "docs/ai-governance/05-accessibility-and-inclusive-design.md"
require_file "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md"
require_file "docs/ai-governance/07-ui-copy-and-microcopy.md"
require_file "docs/ai-governance/08-state-design-and-error-recovery.md"
require_file "docs/ai-governance/09-ai-agent-review-protocol.md"
require_file "docs/ai-governance/10-utility-user-goal-and-product-fit.md"
require_file "docs/ai-governance/11-efficiency-and-expert-use.md"
require_file "docs/ai-governance/12-satisfaction-trust-and-emotional-ux.md"
require_file "docs/ai-governance/13-maintenance-policy.md"
require_file "docs/ai-governance/14-issue-quality-gate.md"
require_file "docs/ai-governance/templates/uiux-review-report.md"
require_file "docs/ai-governance/templates/state-matrix.md"
require_file "docs/ai-governance/templates/novice-simulation.md"
require_file "docs/ai-governance/templates/counter-review.md"
require_file "docs/ai-governance/templates/completion-gate-report.md"
require_file "docs/ai-governance/templates/user-goal-assessment.md"
require_file "docs/ai-governance/templates/efficiency-review.md"
require_file "docs/ai-governance/templates/trust-satisfaction-review.md"
require_file "docs/ai-governance/checklists/p0-p1-p2.md"
require_file "docs/ai-governance/checklists/accessibility.md"
require_file "docs/ai-governance/checklists/cognitive-walkthrough.md"
require_file "docs/ai-governance/checklists/visual-hierarchy.md"
require_file "docs/ai-governance/checklists/content-stress.md"
require_file "docs/ai-governance/checklists/utility-user-goal.md"
require_file "docs/ai-governance/checklists/efficiency.md"
require_file "docs/ai-governance/checklists/satisfaction-trust.md"

ISSUE_TEMPLATES=(
  ".github/ISSUE_TEMPLATE/feature.md"
  ".github/ISSUE_TEMPLATE/bug.md"
  ".github/ISSUE_TEMPLATE/investigation.md"
  ".github/ISSUE_TEMPLATE/operations.md"
)

for template in "${ISSUE_TEMPLATES[@]}"; do
  require_file "$template"
  grep -q "^## 現在のユーザー体験$" "$template" || fail "$template must require the current user experience"
  grep -q "^## 対応後に目指すユーザー体験$" "$template" || fail "$template must require the target user experience"
  grep -q "根拠区分（該当するものを残す）: ユーザー申告 / 実ユーザー観察 / 観測事実からの推定 / 未確認の仮説" "$template" || fail "$template must distinguish the basis of subjective experience"
done

CLAUDE_CONTENT="$(tr -d '\r' < CLAUDE.md | sed '/^[[:space:]]*$/d')"
[[ "$CLAUDE_CONTENT" == "@AGENTS.md" ]] || fail "CLAUDE.md must contain only @AGENTS.md"

if [[ -d ".cursor" ]]; then
  fail ".cursor directory must not be created by this kit"
fi

grep -q "ユーザー価値" AGENTS.md || fail "AGENTS.md must include user value gate"
grep -q "熟練者" AGENTS.md || fail "AGENTS.md must include expert efficiency gate"
grep -q "満足感" AGENTS.md || fail "AGENTS.md must include satisfaction/trust gate"
grep -q "反証レビュー" AGENTS.md || fail "AGENTS.md must include counter-review"
grep -q "背景・判断理由" AGENTS.md || fail "AGENTS.md must require issue rationale"
grep -q "現在のユーザー体験と対応後に目指すユーザー体験" AGENTS.md || fail "AGENTS.md must require current and target user experiences"
grep -q "14-issue-quality-gate.md" AGENTS.md || fail "AGENTS.md must reference issue quality gate"
grep -q "体験が直接変わらない Issue" docs/ai-governance/14-issue-quality-gate.md || fail "issue quality gate must cover issues without a direct user-experience change"
grep -q "コードレビュー往復は最大 10 回" AGENTS.md || fail "AGENTS.md must cap code-review rounds at 10"
grep -q "P1 を含むレビュー結果は、1 PR あたり 3 回まで" AGENTS.md || fail "AGENTS.md must cap P1 review rounds at 3"
grep -q "P0 または P1 を含まないレビュー結果が 3 回連続" AGENTS.md || fail "AGENTS.md must define the three consecutive non-P1 completion condition"
grep -q "PR をマージ可能な完了状態として報告する" AGENTS.md || fail "AGENTS.md must not close a merge-ready PR without explicit instruction"
grep -q "第 4 回の P1" AGENTS.md || fail "AGENTS.md must require follow-up scope split after the third P1"
grep -q "アプリ本体 UI" AGENTS.md || fail "AGENTS.md must distinguish the product application UI"
grep -q "GitHub 共同作業面" AGENTS.md || fail "AGENTS.md must distinguish GitHub collaboration surfaces"
grep -q "ブラウザに表示されるかではなく" AGENTS.md || fail "AGENTS.md must classify UI by ownership instead of browser rendering"
grep -q "GitHub 共同作業面の証跡" docs/ai-governance/03-evidence-and-completion-gates.md || fail "evidence gates must define GitHub collaboration evidence"
grep -q "GitHub 上に表示されることだけを理由にアプリ本体 UI と分類しません" docs/ai-governance/01-agent-operating-contract.md || fail "operating contract must distinguish GitHub rendering from app UI ownership"
grep -q "GitHub 上に表示されるという理由だけで以下の全手順を適用しません" .agents/skills/ui-ux-review/SKILL.md || fail "UI/UX skill must not route every GitHub-rendered change through the full app UI workflow"
grep -q "対象面を「アプリ本体 UI / GitHub 共同作業面 / 混在 / N/A」から選ぶ" .github/pull_request_template.md || fail "PR template must classify app UI and GitHub collaboration surfaces"
grep -q "^---" .agents/skills/ui-ux-review/SKILL.md || fail "Skill frontmatter missing"
grep -q "name: ui-ux-review" .agents/skills/ui-ux-review/SKILL.md || fail "Skill name missing"
grep -q "description:" .agents/skills/ui-ux-review/SKILL.md || fail "Skill description missing"

echo "AI governance verification: PASS"
