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

require_line() {
  local file="$1"
  local line="$2"
  grep -Fxq -- "$line" "$file" || fail "$file must contain the exact line: $line"
}

reject_text() {
  local file="$1"
  local pattern="$2"
  if grep -Fq -- "$pattern" "$file"; then
    fail "$file contains out-of-scope instruction: $pattern"
  fi
}

bash scripts/verify-agent-harness.sh

REQUIRED_FILES=(
  ".agents/skills/ui-ux-review/SKILL.md"
  "docs/ai-governance/00-index.md"
  "docs/ai-governance/glossary.md"
  "docs/ai-governance/01-agent-operating-contract.md"
  "docs/ai-governance/02-uiux-review-framework.md"
  "docs/ai-governance/03-evidence-and-completion-gates.md"
  "docs/ai-governance/04-cognitive-psychology-principles.md"
  "docs/ai-governance/05-accessibility-and-inclusive-design.md"
  "docs/ai-governance/06-visual-hierarchy-and-information-architecture.md"
  "docs/ai-governance/07-ui-copy-and-microcopy.md"
  "docs/ai-governance/08-state-design-and-error-recovery.md"
  "docs/ai-governance/09-ai-agent-review-protocol.md"
  "docs/ai-governance/10-utility-user-goal-and-product-fit.md"
  "docs/ai-governance/11-efficiency-and-expert-use.md"
  "docs/ai-governance/12-satisfaction-trust-and-emotional-ux.md"
  "docs/ai-governance/13-maintenance-policy.md"
  "docs/ai-governance/14-issue-quality-gate.md"
  "docs/ai-governance/templates/uiux-review-report.md"
  "docs/ai-governance/templates/state-matrix.md"
  "docs/ai-governance/templates/novice-simulation.md"
  "docs/ai-governance/templates/counter-review.md"
  "docs/ai-governance/templates/completion-gate-report.md"
  "docs/ai-governance/templates/user-goal-assessment.md"
  "docs/ai-governance/templates/efficiency-review.md"
  "docs/ai-governance/templates/trust-satisfaction-review.md"
  "docs/ai-governance/templates/agent-task-prompt.md"
  "docs/ai-governance/checklists/p0-p1-p2.md"
  "docs/ai-governance/checklists/accessibility.md"
  "docs/ai-governance/checklists/cognitive-walkthrough.md"
  "docs/ai-governance/checklists/visual-hierarchy.md"
  "docs/ai-governance/checklists/content-stress.md"
  "docs/ai-governance/checklists/utility-user-goal.md"
  "docs/ai-governance/checklists/efficiency.md"
  "docs/ai-governance/checklists/satisfaction-trust.md"
)

for file in "${REQUIRED_FILES[@]}"; do
  require_file "$file"
done

# #615で既存正本へ統合した内容を、旧番号の正本・専用checklist・専用verifierへ
# 戻さない。走査対象はcanonical REQUIRED_FILESから導出し、過去reportは走査しない。
RETIRED_PARALLEL_PATHS=(
  "docs/ai-governance/15-interface-engineering-quality.md"
  "docs/ai-governance/16-change-scoped-interface-review.md"
  "docs/ai-governance/checklists/interface-engineering.md"
  "docs/ai-governance/checklists/change-scoped-interface-review.md"
  "scripts/verify-ui-quality-governance.sh"
)

find_retired_markdown_destination() {
  local file="$1"
  local source_path="$2"
  shift 2
  python3 - "$file" "$source_path" "$ROOT" "$@" <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt


file_name, source_path, root, *retired_paths = sys.argv[1:]
source = open(file_name, encoding="utf-8").read()
source_file = os.path.normpath(os.path.join(root, source_path))
source_dir = os.path.dirname(source_file)
retired_targets = {
    os.path.normpath(os.path.join(root, retired_path)): retired_path
    for retired_path in retired_paths
}


def local_destination_path(raw_destination):
    destination = unquote(raw_destination.strip())
    parsed = urlsplit(destination)
    if parsed.scheme or parsed.netloc:
        return None
    return parsed.path or None


for token in MarkdownIt("commonmark").parse(source):
    if token.type != "inline":
        continue
    for child in token.children or []:
        if child.type == "link_open":
            raw_destination = child.attrGet("href")
        elif child.type == "image":
            raw_destination = child.attrGet("src")
        else:
            continue
        if not raw_destination:
            continue
        destination = local_destination_path(raw_destination)
        if destination is None:
            continue
        candidates = {
            os.path.normpath(os.path.join(source_dir, destination)),
            os.path.normpath(os.path.join(root, destination.lstrip("/"))),
        }
        for candidate in candidates:
            retired_path = retired_targets.get(candidate)
            if retired_path is not None:
                print(retired_path)
                raise SystemExit(0)

raise SystemExit(1)
PY
}

# root-relative、canonical fileからのlocal相対path、reference linkを検査し、
# URL・code・近似文字列は対象外にする回帰fixture。
if ! find_retired_markdown_destination \
  <(printf '%s\n' '## Fixture' '[legacy](15-interface-engineering-quality.md)') \
  "docs/ai-governance/03-evidence-and-completion-gates.md" \
  "${RETIRED_PARALLEL_PATHS[@]}" >/dev/null; then
  fail "retired markdown destination fixture was not detected"
fi
if ! find_retired_markdown_destination \
  <(printf '%s\n' '## Fixture' '[legacy](docs/ai-governance/15-interface-engineering-quality.md)') \
  "docs/ai-governance/00-index.md" \
  "${RETIRED_PARALLEL_PATHS[@]}" >/dev/null; then
  fail "root-relative retired markdown destination fixture was not detected"
fi
if ! find_retired_markdown_destination \
  <(printf '%s\n' '## Fixture' '[legacy][old]' '' '[old]: docs/ai-governance/15-interface-engineering-quality.md') \
  "docs/ai-governance/00-index.md" \
  "${RETIRED_PARALLEL_PATHS[@]}" >/dev/null; then
  fail "reference-link retired markdown destination fixture was not detected"
fi
if find_retired_markdown_destination \
  <(printf '%s\n' '## Fixture' '    [legacy](15-interface-engineering-quality.md)' '[safe](15-interface-engineering-quality.md.bak)' '[external](https://example.test/15-interface-engineering-quality.md)') \
  "docs/ai-governance/03-evidence-and-completion-gates.md" \
  "${RETIRED_PARALLEL_PATHS[@]}" >/dev/null; then
  fail "retired markdown destination fixture accepted a false positive"
fi

for retired_path in "${RETIRED_PARALLEL_PATHS[@]}"; do
  if [[ -e "$retired_path" || -L "$retired_path" ]]; then
    fail "retired parallel governance path must not be restored: $retired_path"
  fi
done

RETIRED_REFERENCE_PATHS=("${REQUIRED_FILES[@]}")

for file in "${RETIRED_REFERENCE_PATHS[@]}"; do
  for retired_path in "${RETIRED_PARALLEL_PATHS[@]}"; do
    reject_text "$file" "$retired_path"
  done
  if retired_destination="$(find_retired_markdown_destination "$file" "$file" "${RETIRED_PARALLEL_PATHS[@]}")"; then
    fail "$file contains retired parallel markdown destination: $retired_destination"
  fi
done

ISSUE_TEMPLATES=(
  ".github/ISSUE_TEMPLATE/feature.md"
  ".github/ISSUE_TEMPLATE/bug.md"
  ".github/ISSUE_TEMPLATE/investigation.md"
  ".github/ISSUE_TEMPLATE/operations.md"
)

for template in "${ISSUE_TEMPLATES[@]}"; do
  require_file "$template"
  require_line "$template" "## 現在のユーザー体験"
  require_line "$template" "## 対応後に目指すユーザー体験"
  require_text "$template" "根拠区分（該当するものを残す）: ユーザー申告 / 実ユーザー観察 / 観測事実からの推定 / 未確認の仮説"
done

require_line ".github/ISSUE_TEMPLATE/bug.md" "name: Bug Report"
require_line ".github/ISSUE_TEMPLATE/bug.md" "title: \"[Bug]: \""
require_line ".github/ISSUE_TEMPLATE/feature.md" "name: Feature / Improvement"
require_line ".github/ISSUE_TEMPLATE/feature.md" "title: \"[Feature]: \""
require_line ".github/ISSUE_TEMPLATE/investigation.md" "name: Investigation"
require_line ".github/ISSUE_TEMPLATE/investigation.md" "title: \"[Investigation]: \""
require_line ".github/ISSUE_TEMPLATE/operations.md" "name: Operations / Production Investigation"
require_line ".github/ISSUE_TEMPLATE/operations.md" "title: \"[Ops]: \""
reject_text ".github/ISSUE_TEMPLATE/bug.md" "title: \"[不具合] \""
reject_text ".github/ISSUE_TEMPLATE/feature.md" "title: \"[改善] \""
reject_text ".github/ISSUE_TEMPLATE/investigation.md" "title: \"[調査] \""
reject_text ".github/ISSUE_TEMPLATE/operations.md" "title: \"[運用] \""

require_line ".github/ISSUE_TEMPLATE/review-follow-up.md" "name: レビュー指摘のフォローアップ"
require_line ".github/ISSUE_TEMPLATE/review-follow-up.md" "title: \"[レビュー指摘] \""
require_line ".github/ISSUE_TEMPLATE/review-follow-up.md" "labels: レビュー指摘"
REVIEW_FOLLOW_UP_SECTIONS=(
  "## 由来"
  "## 重要度（severity）"
  "## 観測事実"
  "## 影響"
  "## 別追跡の理由"
  "## 現在のユーザー体験（UX）"
  "## 対応後に目指すユーザー体験（UX）"
  "## 対応範囲（scope）"
  "## 受け入れ条件（acceptance）"
  "## 検証方針（verification）"
  "## 公開安全性"
)
for section in "${REVIEW_FOLLOW_UP_SECTIONS[@]}"; do
  require_line ".github/ISSUE_TEMPLATE/review-follow-up.md" "$section"
done
REVIEW_FOLLOW_UP_FIELDS=(
  "- 対象PR:"
  "- 対象review:"
  "- severity:"
  "- 確認済み事実:"
  "- 利用者への影響:"
  "- 別追跡の理由:"
  "- 対象ユーザーと利用文脈:"
  "根拠区分（該当するものを残す）: ユーザー申告 / 実ユーザー観察 / 観測事実からの推定 / 未確認の仮説"
  "- scope:"
  "- acceptance:"
  "- verification:"
  "- 公開安全性の確認:"
)
for field in "${REVIEW_FOLLOW_UP_FIELDS[@]}"; do
  require_text ".github/ISSUE_TEMPLATE/review-follow-up.md" "$field"
done

require_text "docs/ai-governance/14-issue-quality-gate.md" "Issue と PR のタイトル・本文は日本語を原則とします。"
require_text "docs/ai-governance/14-issue-quality-gate.md" "固有名詞、製品名・ライブラリ名"
require_text "docs/ai-governance/14-issue-quality-gate.md" "一般的なIssueカテゴリの接頭辞は原表記を維持"
require_text "docs/ai-governance/14-issue-quality-gate.md" "タイトルは、対象と変更または問題が判別できる具体性"
require_text "docs/ai-governance/14-issue-quality-gate.md" "レビュー結果を主因として別Issueを作成する場合"
require_text "docs/ai-governance/14-issue-quality-gate.md" "タイトルを \`[レビュー指摘] <日本語要約>\`"
require_text "docs/ai-governance/14-issue-quality-gate.md" "\`レビュー指摘\` ラベルを付けます。"
require_text "docs/ai-governance/14-issue-quality-gate.md" "由来PR・review、\`severity\`、観測事実、影響、別追跡の理由"
require_text "docs/ai-governance/14-issue-quality-gate.md" "レビューのURLやPR・CIの参照だけで、レビュー起因とは分類しません。"
require_text "docs/ai-governance/14-issue-quality-gate.md" "根拠が不足している場合は、レビュー起因のラベルやprefixを推測で付けません。"
require_text "docs/ai-governance/14-issue-quality-gate.md" "同一PRのレビュー修正は、そのPRの主Issueを継続して追跡"
require_text "docs/ai-governance/14-issue-quality-gate.md" "P0、P1、security、secret、data integrity、受入証跡の矛盾"
require_text "docs/ai-governance/14-issue-quality-gate.md" "別Issue化を理由にblockingを解除しません。"

require_text ".agents/skills/github-delivery/SKILL.md" "14-issue-quality-gate.md"
require_text ".agents/skills/github-delivery/SKILL.md" "Issueのタイトルと本文は日本語を原則"
require_text ".agents/skills/github-delivery/SKILL.md" "PRのタイトルと本文も日本語を原則"
require_text ".agents/skills/github-delivery/SKILL.md" "自動生成bot PR"
require_text ".agents/skills/github-delivery/SKILL.md" "タイトルと本文を正規化"
require_text ".agents/skills/github-delivery/SKILL.md" "\`[レビュー指摘]\` title"
require_text ".agents/skills/ui-ux-review/SKILL.md" "name: ui-ux-review"
require_text ".agents/skills/ui-ux-review/SKILL.md" "アプリ本体UI"
require_text ".agents/skills/ui-ux-review/SKILL.md" "GitHub共同作業面"
require_text ".agents/skills/ui-ux-review/SKILL.md" "state matrix"
require_text ".agents/skills/ui-ux-review/SKILL.md" "現在の監査実行"
require_text ".agents/skills/ui-ux-review/SKILL.md" "取得手段、開始状態、完了状態、重要な分岐"
require_text ".agents/skills/ui-ux-review/SKILL.md" "各ステップの安定後に画面を取得"
require_text ".agents/skills/ui-ux-review/SKILL.md" "保存した画像そのものを検査"
require_text ".agents/skills/ui-ux-review/SKILL.md" "完全なフロー監査と扱わない"
require_text ".agents/skills/ui-ux-review/SKILL.md" "GitHubが所有する未変更の操作フロー"
require_text ".claude/skills/ui-ux-review/SKILL.md" "フロー監査"
require_text ".claude/skills/ui-ux-review/SKILL.md" "../../../.agents/skills/ui-ux-review/SKILL.md"
require_file ".claude/skills/ui-ux-review/../../../.agents/skills/ui-ux-review/SKILL.md"
reject_text ".agents/skills/ui-ux-review/SKILL.md" "Browser Choice"
reject_text ".agents/skills/ui-ux-review/SKILL.md" "user-context"
reject_text ".agents/skills/ui-ux-review/SKILL.md" "Figma監査ボード"
require_text "docs/ai-governance/02-uiux-review-framework.md" "P0"
require_text "docs/ai-governance/02-uiux-review-framework.md" "観測事実、ユーザー影響、推奨対応、証跡上の限界"
require_text "docs/ai-governance/02-uiux-review-framework.md" "P0 / P1 / P2だけ"
require_text "docs/ai-governance/02-uiux-review-framework.md" "間接資料だけで実際のフローを監査済みと扱いません"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "前後screenshot"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "重要な各ステップ"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "取得不能の具体的なblocker"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "navigation、focus、loading、validation、error recovery、empty state、motion"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "誤画面、誤状態、blank、loading中、文脈を隠すcrop、別window、half-rendered状態"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "screenshotだけではsemantic structure"
require_text "docs/ai-governance/templates/uiux-review-report.md" "フロー監査（発動時）"
require_text "docs/ai-governance/templates/uiux-review-report.md" "screenshot参照またはblocker"
require_text "docs/ai-governance/templates/uiux-review-report.md" "証跡上の限界"
require_text "docs/ai-governance/templates/completion-gate-report.md" "フロー監査（発動時）"
require_text "docs/ai-governance/templates/completion-gate-report.md" "重要ステップの順序付き証跡またはblocker"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "latest meaningful change"
require_text "docs/ai-governance/03-evidence-and-completion-gates.md" "GitHubのmergeabilityがclean"
require_text "docs/ai-governance/14-issue-quality-gate.md" "体験が直接変わらない Issue"
require_text ".github/pull_request_template.md" "PRのタイトルと本文は日本語を原則とします。"
require_line ".github/pull_request_template.md" "## 関連Issue"
require_line ".github/pull_request_template.md" "## UI/UX・GitHub共同作業面の証跡"
require_line ".github/pull_request_template.md" "## CI / レビュー"
require_text ".github/pull_request_template.md" "- 関連Issue:"
require_text ".github/pull_request_template.md" "- 対象面:"
require_text ".github/pull_request_template.md" "- 最新コミット:"
require_text ".github/pull_request_template.md" "- push時CI (push CI):"
require_text ".github/pull_request_template.md" "- pull_request時CI (pull_request CI):"
require_text ".github/pull_request_template.md" "- 最新の意味ある変更への自動・人間レビュー"
require_text ".github/pull_request_template.md" "- GitHubのマージ可能性 (GitHub mergeability):"
require_text ".github/pull_request_template.md" "## 未実行の検証"
require_text ".github/pull_request_template.md" "## 残るリスク"
reject_text ".github/pull_request_template.md" "## Issue"
reject_text ".github/pull_request_template.md" "## CI / Review"
require_text ".github/workflows/agent-harness.yml" "- '.github/dependabot.yml'"
require_text ".github/dependabot.yml" "      - dependencies"
require_text ".github/dependabot.yml" "      - 依存関係更新"
require_text ".github/dependabot.yml" "      prefix: \"依存関係更新\""
DEPENDABOT_UPDATE_COUNT="$(grep -Fc -- "  - package-ecosystem:" .github/dependabot.yml)"
DEPENDABOT_LABEL_COUNT="$(grep -Fc -- "      - 依存関係更新" .github/dependabot.yml)"
DEPENDABOT_PREFIX_COUNT="$(grep -Fc -- "      prefix: \"依存関係更新\"" .github/dependabot.yml)"
[[ "$DEPENDABOT_UPDATE_COUNT" -gt 0 ]] || fail ".github/dependabot.yml must define at least one update"
[[ "$DEPENDABOT_LABEL_COUNT" -eq "$DEPENDABOT_UPDATE_COUNT" ]] || fail ".github/dependabot.yml must label every update with 依存関係更新"
[[ "$DEPENDABOT_PREFIX_COUNT" -eq "$DEPENDABOT_UPDATE_COUNT" ]] || fail ".github/dependabot.yml must prefix every update with 依存関係更新"
require_text "docs/ai-governance/templates/completion-gate-report.md" "push CI"
require_text "docs/ai-governance/templates/completion-gate-report.md" "pull_request CI"
require_text "docs/ai-governance/templates/completion-gate-report.md" "GitHub mergeability"

echo "AI governance verification: PASS"
