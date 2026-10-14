---
name: github-delivery
description: "WordPack固有のCI gate選択とIssue / PR公開文書の参照を確認するときに使う。"
---

# WordPack CI・公開文書の参照

## 適用範囲

このSkillはrepository固有のCI構成、検証入口、Issue / PR文書の品質・公開安全性の参照先を示します。共通の作業手順や配送権限は利用環境のローカル規則とユーザー依頼に従います。

## CI gate

- workflowのtriggerとjobは[`.github/workflows/ci.yml`](../../../.github/workflows/ci.yml)を参照します。
- changed pathに応じたgate選択と分類失敗時の扱いは[`scripts/classify_verification_inputs.py`](../../../scripts/classify_verification_inputs.py)を参照します。
- 各gateの選択条件、対応コマンド、成果物は[`docs/testing/index.md`](../../../docs/testing/index.md)に記載します。
- governance文書のfrontmatter、参照、source-size、任意task-state形式は`python3 scripts/validate_governance.py`でstatic確認します。この結果はClaude Code / Cursorのruntime、ローカル規則の読込、production挙動を証明しません。

## Issue / PR文書

- Issue本文のWordPack向け品質項目は[`docs/ai-governance/14-issue-quality-gate.md`](../../../docs/ai-governance/14-issue-quality-gate.md)を参照します。
- Issue / PR、report、sampleなど公開物の機密情報・実識別子確認は[公開安全性Skill](../security-publication/SKILL.md)と[`docs/security-publication-checklist.md`](../../../docs/security-publication-checklist.md)を参照します。
