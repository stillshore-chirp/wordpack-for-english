# ガバナンス保守方針

この文書は、AIエージェント向けルールとUI/UXガバナンスを保守する方針です。3製品の全体構成と委任・証跡契約は [`docs/agent-harness.md`](../agent-harness.md) を正本とします。

## 正本

- 共通の常時読込契約: `AGENTS.md`
- 領域固有契約: 対象に最も近い`AGENTS.md`
- task手順: `.agents/skills/<name>/SKILL.md`
- UI/UX・Issue・完了条件: `docs/ai-governance/`
- Claude Code / Cursor接続: `.claude/`、`.cursor/`の薄いadapter
- 機械検査: `scripts/validate_governance.py`

adapterは正本への接続だけを持ち、独自のhard gateや長い本文を持ちません。正本が複数ある場合は、一つを選び、他は要約と参照にします。

## 3製品と配置

Codexはrootと最寄りのnested `AGENTS.md`、task Skillを読みます。Claude Codeは`CLAUDE.md`とpath rule、Skill adapterから同じ正本へ到達します。Cursorはroot契約と`alwaysApply: false`のMDC ruleから同じ正本へ到達します。いずれもadapterの発動失敗だけで共通の安全境界を失わない構成にします。

新しいルールは、全作業共通ならroot、path固有ならnested rule、作業種類固有ならSkill、形式や参照など自動判定可能なら検査scriptへ置きます。既存正本へ統合できる場合は新しい文書を増やしません。

## instruction budget

`validate_governance.py`は次の上限を検査します。

| 対象 | 行 | byte |
|---|---:|---:|
| root `AGENTS.md` | 180 | 16384 |
| nested `AGENTS.md` | 100 | 8192 |
| `.claude` / `.cursor` adapter | 30 | 4096 |
| canonical Skill | 180 | 16384 |
| root + one nested `AGENTS.md` | — | 24576 |

値はsource-sizeのestimateです。製品のtoken telemetryやHook注入量をobserved usageとして扱いません。

## 保守時の確認

変更前に対象path、正本、adapter、Skill、必要な検証を確認します。変更後は正本への到達性、重要リンク、frontmatter、budget、公開安全性を検査し、未実行の確認と残るriskを報告します。

委任・timeout・re-wait、evidenceのinput closure単位の再利用、runtime resourceのownerとcleanup、primary例外の7項目は `docs/agent-harness.md` の契約を維持します。ここへ同じfield表や状態遷移を複製しません。

レビュー・CIの取得順序と配送判断は [GitHub配送Skill](../../.agents/skills/github-delivery/SKILL.md)、実行コマンドとpath別testは [`docs/testing/index.md`](../testing/index.md) を参照します。検査scriptはreviewや製品runtimeの代替ではありません。

## Skill Evaluation

Skill Evaluationはfrontmatter、発動条件、progressive disclosure、参照、責務重複、budget、公開安全なsynthetic設定をstaticに確認します。認証・費用・隔離workspace・外部runnerを確定できないlive benchmarkは開始せず、static結果をlive成功と報告しません。

## 停止条件

共通hard gateへ到達できない、adapterだけに重要な判断基準がある、正本間で条件が食い違う、budget超過を未整理のまま残す、壊れたlinkや未確認の公開範囲がある場合は、完了扱いにせず理由と次の確認を残します。
