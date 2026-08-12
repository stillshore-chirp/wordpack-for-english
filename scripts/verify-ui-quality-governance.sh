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

require_text() {
  local file="$1"
  local pattern="$2"
  grep -Fq -- "$pattern" "$file" || fail "$file must contain: $pattern"
}

require_any_text() {
  local file="$1"
  shift
  local pattern
  for pattern in "$@"; do
    if grep -Fiq -- "$pattern" "$file"; then
      return 0
    fi
  done
  fail "$file must contain one of: $*"
}

reject_pattern_in_changed_governance() {
  local pattern="$1"
  if grep -REini --exclude-dir='.git' -- "$pattern" \
    .agents/skills/ui-ux-review \
    docs/ai-governance \
    scripts/verify-ui-quality-governance.sh; then
    fail "external-source-specific text or runtime dependency found: $pattern"
  fi
}

REQUIRED_FILES=(
  ".agents/skills/ui-ux-review/SKILL.md"
  "docs/ai-governance/00-index.md"
  "docs/ai-governance/02-uiux-review-framework.md"
  "docs/ai-governance/03-evidence-and-completion-gates.md"
  "docs/ai-governance/05-accessibility-and-inclusive-design.md"
  "docs/ai-governance/09-ai-agent-review-protocol.md"
  "docs/ai-governance/15-interface-engineering-quality.md"
  "docs/ai-governance/16-change-scoped-interface-review.md"
  "docs/ai-governance/templates/uiux-review-report.md"
  "docs/ai-governance/templates/completion-gate-report.md"
  "docs/ai-governance/checklists/interface-engineering.md"
  "docs/ai-governance/checklists/change-scoped-interface-review.md"
)

for file in "${REQUIRED_FILES[@]}"; do
  require_file "$file"
done

# Skillから必要時だけ詳細正本へ到達できること。
require_text ".agents/skills/ui-ux-review/SKILL.md" "15-interface-engineering-quality.md"
require_text ".agents/skills/ui-ux-review/SKILL.md" "16-change-scoped-interface-review.md"
require_text ".agents/skills/ui-ux-review/SKILL.md" "Introduced / Regression / Pre-existing"
require_text ".agents/skills/ui-ux-review/SKILL.md" "verify-ui-quality-governance.sh"

# 実装品質の最低coverage。
IMPLEMENTATION="docs/ai-governance/15-interface-engineering-quality.md"
require_text "$IMPLEMENTATION" "container query"
require_text "$IMPLEMENTATION" "RTL"
require_text "$IMPLEMENTATION" "tabular numbers"
require_text "$IMPLEMENTATION" "semantic token"
require_text "$IMPLEMENTATION" "prefers-reduced-motion"
require_text "$IMPLEMENTATION" "transition: all"
require_text "$IMPLEMENTATION" "320 CSS px"
require_text "$IMPLEMENTATION" "200%"

# Accessibilityの実装判断と手動検証。
ACCESSIBILITY="docs/ai-governance/05-accessibility-and-inclusive-design.md"
require_text "$ACCESSIBILITY" "Native semantics"
require_text "$ACCESSIBILITY" "Focus表示・移動・復帰"
require_text "$ACCESSIBILITY" "複合widget"
require_text "$ACCESSIBILITY" "live region"
require_text "$ACCESSIBILITY" "forced colors"
require_text "$ACCESSIBILITY" "prefers-reduced-motion"
require_text "$ACCESSIBILITY" "320 CSS px"
require_text "$ACCESSIBILITY" "200% zoom"
require_text "$ACCESSIBILITY" "自動検査だけで合格としない"

# 変更差分reviewのscope・削除側・分類・read-only境界。
CHANGE_REVIEW="docs/ai-governance/16-change-scoped-interface-review.md"
require_text "$CHANGE_REVIEW" "Base"
require_text "$CHANGE_REVIEW" "Head"
require_text "$CHANGE_REVIEW" "追加行と削除行を読む"
require_text "$CHANGE_REVIEW" "Introduced"
require_text "$CHANGE_REVIEW" "Regression"
require_text "$CHANGE_REVIEW" "Pre-existing"
require_text "$CHANGE_REVIEW" "Fileではなく利用者面へ展開する"
require_text "$CHANGE_REVIEW" "Read-only review"
require_text "$CHANGE_REVIEW" "直前commitへ勝手に切り替えません"

# Protocolと証跡形式が正本を実行可能な形へ接続すること。
require_text "docs/ai-governance/09-ai-agent-review-protocol.md" "base / head"
require_text "docs/ai-governance/09-ai-agent-review-protocol.md" "追加側・削除側"
require_text "docs/ai-governance/09-ai-agent-review-protocol.md" "Pre-existing"
require_text "docs/ai-governance/templates/uiux-review-report.md" "Domain coverage"
require_text "docs/ai-governance/templates/uiux-review-report.md" "Introduced / Regression findings"
require_text "docs/ai-governance/templates/uiux-review-report.md" "Pre-existing findings"
require_text "docs/ai-governance/templates/uiux-review-report.md" "検討したがfindingにしなかった候補"
require_text "docs/ai-governance/templates/completion-gate-report.md" "Change status"

# Indexが入口として新規正本と検証へ到達すること。
require_text "docs/ai-governance/00-index.md" "15-interface-engineering-quality.md"
require_text "docs/ai-governance/00-index.md" "16-change-scoped-interface-review.md"
require_text "docs/ai-governance/00-index.md" "verify-ui-quality-governance.sh"

# 常時読込量を守り、Skillへ詳細正本を複製しすぎないこと。
skill_lines="$(wc -l < .agents/skills/ui-ux-review/SKILL.md | tr -d ' ')"
skill_bytes="$(wc -c < .agents/skills/ui-ux-review/SKILL.md | tr -d ' ')"
(( skill_lines <= 180 )) || fail "ui-ux-review Skill exceeds 180 lines: $skill_lines"
(( skill_bytes <= 16384 )) || fail "ui-ux-review Skill exceeds 16384 bytes: $skill_bytes"

# 外部成果物への実行時依存や固有名を正本へ持ち込まない。
reject_pattern_in_changed_governance 'jakub|krehel|interfaces\.dev|skills\.sh/jakub|github\.com/jakubkrehel'
reject_pattern_in_changed_governance 'better-(interface|accessibility|layout|writing|typography|colors|ui)'

# shell自身の構文も退行させない。
bash -n scripts/verify-ui-quality-governance.sh

echo "UI quality governance verification: PASS"
