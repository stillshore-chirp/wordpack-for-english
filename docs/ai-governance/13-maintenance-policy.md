# ガバナンス保守方針

この文書は、AIエージェント向けルールとUI/UXガバナンスを保守するための方針です。Codex・Claude Code・Cursorを同時に支援する全体構成は [`docs/agent-harness.md`](../agent-harness.md) を正本とします。

## 正本

- 共通の常時読込契約: `AGENTS.md`
- 領域固有契約: 対象に最も近いnested `AGENTS.md`
- task固有手順: `.agents/skills/<name>/SKILL.md`
- UI/UX詳細: `docs/ai-governance/`
- 公開安全性詳細: `docs/security-publication-checklist.md`
- Claude Code adapter: `.claude/rules/`, `.claude/skills/`
- Cursor adapter: `.cursor/rules/`
- 機械検証: `scripts/verify-agent-harness.sh`, `scripts/verify-ai-governance.sh`

`CLAUDE.md` は `@AGENTS.md` だけを原則とします。tool adapterは正本を参照するだけで、新しい判断基準を持ちません。

### 正本参照とeffective instruction budget（唯一正本）

実効instruction budgetの定義と計測手順はこの節を唯一の正本とします。`global / user-level`、repository root、nested rule、activated Skill、条件成立時のconditional hook contextを合算して評価し、portableなexplicit-input計測（対象revision、適用path、発動条件、入力資料を明示）を使います。推定値（estimate）と実行で得た値（observed usage）を分離して記録し、Hookが未発動または実測できない場合は実効量を推定値として扱い、runtime enforcementの証拠にしません。

## 変更時の3製品確認

ルール、Skill、adapter、検証scriptを変更する場合は、同じPRで次を確認します。

### Codex

- rootとnested `AGENTS.md`から必要な規則へ到達できる。
- task手順が常時読込へ混入せず、`.agents/skills/`へ分離されている。
- rootとnestedの合計がinstruction budgetを満たす。

### Claude Code

- `CLAUDE.md`が共通核を一重にimportしている。
- path固有の規則が`.claude/rules/`の`paths`で必要時だけ案内される。
- task手順が`.claude/skills/`の薄いadapterから共有Skillへ接続される。
- adapterへ長文の本文をコピーしていない。

### Cursor

- root `AGENTS.md`と`.cursor/rules/`が競合せず、MDC ruleは`alwaysApply: false`と適切な`globs`を持つ。
- task手順は`.agents/skills/`を正本として利用できる。
- `.cursor`ディレクトリの存在を禁止しない。
- ruleへ共通核やSkill本文を複製していない。

## ルール追加の判断

1. 全作業で必要ならroot `AGENTS.md`。
2. 特定pathだけならnested `AGENTS.md`と薄いtool adapter。
3. 特定taskだけなら`.agents/skills/`と必要なadapter。
4. 機械判定できるならscript、test、lint、CI。
5. 既存正本へ統合できる場合は新規文書を増やさない。

詳細手順をrootへ追加する変更は、他の配置では成立しない理由をIssueとPRへ書きます。

## 重複禁止

同じhard gate、checklist、workflow本文を複数箇所で正本化しません。

良い構造:

```text
AGENTS.md -> task Skill -> 詳細正本
Claude / Cursor adapter -> 同じAGENTSまたはSkill
```

避ける構造:

```text
AGENTS.md、Skill、docs、tool専用ruleに同じ長文を複製
```

表現を少し変えた意味上の重複も対象です。indexは入口、Skillは実行順序、詳細docsは判定基準として責務を分けます。

## Hard gateとheuristic

- P0、secret、証跡捏造、データ破壊、公開契約、権限境界はhard gateとして明確にする。
- ソースコード変更依頼に含まれる通常配送と、別の明示指示が必要なmerge等の権限境界は、rootのhard gate、GitHub配送Skillの実行順序、検証scriptで分担して固定する。
- DRY、KISS、SRP、OCP、行数、重複回数、test配分はheuristicとして扱う。
- heuristicを数値だけのFail条件へ変えない。
- P0を格下げする場合は、完了不可ではない根拠を記録する。

## Review収束
<!-- agent-harness:review-maintenance:start -->

- review回数、review decision record、lane liveness、focused review terminal、停止条件、限定再確認、P2以下の収束、primary ledgerは [`docs/agent-harness.md`](../agent-harness.md)、CI待機、最新snapshot、gate失効は [GitHub配送Skill](../../.agents/skills/github-delivery/SKILL.md) を正本とする。
- root、nested rule、adapterへその本文を複製せず、特定製品のreview名やtool挙動を共有完了条件にしない。
- review未提供を自己レビューで代替しないこと、未解決thread・mergeability・merge / close権限のhard gateを、上記正本の変更時に維持する。
<!-- agent-harness:review-maintenance:end -->

## サブエージェント運用
<!-- agent-harness:subagent-maintenance:start -->

委任、再監査、検証段階、risk lane台帳の正本は [`docs/agent-harness.md`](../agent-harness.md) のSubagent orchestrationとします。root `AGENTS.md`は全agentが到達する短い入口だけを持ち、nested rule、Skill、adapterへ同じ運用本文を複製しません。

運用を変更する時は、積極利用と重複防止の両方を保ちます。新しい専門riskを独立laneへ委任できることを維持しつつ、同一HEADの重複監査、根拠のない再実行、過剰なfork文脈を増やさないことをreviewします。
<!-- agent-harness:subagent-maintenance:end -->

## 研究・標準

新しい研究やガイドラインを取り込む時は、標準・仕様、長く使われるHCI原則、認知アクセシビリティ指針、最新研究、単発研究の順に強制力を判断します。単発研究や製品固有の一時的挙動を、根拠なくhard gateへしません。

公式仕様が変わった場合は、3製品の現行仕様を確認し、adapterと検証scriptを同時に更新します。

## 検証
<!-- agent-harness:maintenance-verification:start -->

実行コマンドと変更path別のtestは [`docs/testing/index.md`](../testing/index.md)、gate選択・包含・失効はGitHub配送Skillを正本とします。変更したshell、YAML、frontmatter、link、公開安全性と、通常配送・review・権限境界が機械検査で退行しないことを確認し、未確認項目は理由とriskを報告します。

変更影響調査の入口を変更する場合は、正本が定める非自明なコード改修、代表的な省略ケース、graphの利用不能・未設定・古い・解析失敗・情報不足時のfallbackを `scripts/verify-agent-harness.sh` の機械検査で確認します。graph結果だけで品質ゲートを弱めず、3製品のadapterへ本文を複製しません。
<!-- agent-harness:maintenance-verification:end -->
