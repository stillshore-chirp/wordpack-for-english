# エージェントハーネス互換性方針

この文書は、Codex、Claude Code、Cursorの3つで、同じ品質契約を過不足なく適用するための詳細正本です。個別製品へ同じ長文を複製せず、共通正本、scope、adapter、Skill、機械検査を組み合わせます。

## 1. 目的

- 重要なhard gateを3エージェントで一貫して適用する。
- 作業に無関係な指示を常時読み込ませない。
- tool固有機能を活用しつつ、特定toolだけで成立するルールを正本にしない。
- ルール追加によるinstruction budgetの無制限な増加を防ぐ。
- 発動漏れ、重複、循環参照、古いadapterをCIで検出する。

## 2. 用語

- **共通正本**: tool非依存の判断基準を置く `AGENTS.md`、`docs/`、`.agents/skills/`。
- **近接ルール**: 特定directory以下にだけ適用する `AGENTS.md`。
- **adapter**: tool固有のscope機構から共通正本へ接続する短いファイル。
- **Skill**: 特定作業でだけ読む実行手順。常時ルールにはしない。
- **hard gate**: 違反した状態で完了または公開してはいけない条件。
- **heuristic**: 文脈に応じて採否を判断する設計・実装上の目安。
- **instruction budget**: 詳細は [`13-maintenance-policy.md`](13-maintenance-policy.md) の「正本参照とeffective instruction budget」を参照する指示量。

## 3. 3エージェントの適用構造

| 対象 | 常時入口 | scopeの絞り方 | 作業手順 | fallback |
|---|---|---|---|---|
| Codex | ルート `AGENTS.md` | 作業pathに近い `AGENTS.md` | `.agents/skills/` | 近接ルールがなければルート契約と関連docs |
| Claude Code | `CLAUDE.md` の `@AGENTS.md` | `.claude/rules/` のpath条件 | 共通Skillを明示参照 | adapterが未発動でもルート契約を維持 |
| Cursor | ルート契約と `.cursor/rules/` | `.cursor/rules/*.mdc` のglobs | 共通Skillを明示参照 | adapterが未発動でもルート契約を維持 |

共通の意味は常に共通正本へ置きます。Claude CodeとCursorのadapterは、適用path、追加で読む近接ルール、使うSkillだけを示します。

## 4. 配置判断

新しいルールは、次の順で配置先を判断します。

1. **機械で判定できるか**: format、lint、schema、禁止pattern、file存在、line budgetはscriptまたはCIへ置く。
2. **常に必要なhard gateか**: 秘密情報、検証捏造、未確認差分、ソースコード変更の配送権限、破壊的操作などに限りルートへ置く。
3. **特定domainだけか**: frontend、backend、operationsなどの近接 `AGENTS.md` へ置く。
4. **特定作業だけか**: UI review、GitHub配送、本番調査、公開審査などのSkillへ置く。
5. **詳細な判断根拠か**: `docs/` の正本へ置く。
6. **tool固有の発動条件か**: `.claude/rules/` または `.cursor/rules/` のadapterへ置く。

ルートへ追加することを既定にしません。

## 5. instruction budget

### 5.1 常時読み込み

- ルート `AGENTS.md` は200行未満をhard gateとし、目標は150行以下とする。
- `CLAUDE.md` は `@AGENTS.md` のみを維持する。
- ルートへcommandの全分岐、template全文、詳細checklist、特定review botの操作手順を置かない。

### 5.2 scoped ruleとadapter

- adapterは40行以下を目標とし、ルール本文を持たない。
- 1つのadapterが複数domainを無関係に束ねない。
- globsまたはpathsは、正本の適用範囲と一致させる。
- adapterから別adapterを参照しない。

### 5.3 Skill

- Skillは発動条件、読む正本、実行順序、成果物、hard gateに集中する。
- 詳細正本と同じ質問・checklistを再掲しない。
- Skillから索引を経由して同じSkillへ戻る循環参照を作らない。
- 1つのSkillへ異なる作業種類を集約しない。

### 5.4 effective instruction budget

定義と計測手順は [`13-maintenance-policy.md`](13-maintenance-policy.md) の「正本参照とeffective instruction budget」を唯一の正本とします。互換性レビューでは、各adapterが同正本の合算対象へ到達できること、portableなexplicit-input計測とestimate / observed usageの分離が保たれることだけを確認します。製品固有のtoken telemetryや、未発動Hookの注入量は互換性の証拠にしません。

## 6. tool中立性

共通正本では、結果と契約を定義します。特定toolの操作方法はadapterまたはSkillの補足に留めます。

良い例:

- 「利用可能な認証済みGitHub clientでIssueとPRを作成する」
- 「latest meaningful changeに対するGitHub上のコードレビュー結果を確認する」
- 「path-scoped adapterから近接ルールを読む」

避ける例:

- すべてのエージェントへ特定CLIの認証commandを必須化する。
- 共通branch名へ特定製品名を固定する。
- 特定review botだけをコードレビューの完了手段として固定する。
- Cursorのrules directoryを禁止する。

tool中立性はレビュー自体を任意にする意味ではありません。ソースコード変更では、GitHub上で確認可能な自動または人間のコードレビューを必須とし、特定botがなくても同等のreview経路を使います。いずれのreview経路も提供されない場合は未完了です。

## 7. hard gateとheuristic

ルール追加時は命令強度を明記します。

### hard gateにできる条件

- 違反時の具体的な損害または虚偽が説明できる。
- Pass / Failを観測可能な証跡で判定できる。
- 3エージェントで同じ意味に解釈できる。
- 例外が必要な場合、その承認条件が定義されている。

### heuristicとして扱う条件

- DRY、抽象化、file分割、layering、test配置など、複数の妥当な解がある設計判断。
- 行数、重複回数、component粒度など、contextで妥当値が変わる目安。
- 将来拡張、再利用可能性、pattern採用など、trade-offを伴う判断。

heuristicを採用しないこと自体を失敗にせず、品質・保守性へ実質的なリスクがある場合だけ指摘します。

## 8. ハーネス変更時の互換性レビュー

エージェントルール、Skill、adapter、検証scriptを変更するPRでは、次を確認します。

review decision recordと停止条件は [`docs/agent-harness.md`](../agent-harness.md) を正本とし、3製品のadapterとrepository verifierが同じmarkerへ到達できることだけを互換性観点で確認します。field定義やレビュー回数の本文は複製しません。

| 観点 | Codex | Claude Code | Cursor |
|---|---|---|---|
| 依頼解釈 | ソースコード変更で配送Skillが発動するか | root契約経由で同じ発動条件になるか | root契約経由で同じ発動条件になるか |
| 発見 | root / nested `AGENTS.md`から到達できるか | `CLAUDE.md` / path ruleから到達できるか | `.cursor/rules`のglobsから到達できるか |
| scope | 無関係directoryへ適用されないか | pathsが広すぎないか | globs / alwaysApplyが広すぎないか |
| 正本 | tool固有copyを作っていないか | adapterに本文を複製していないか | adapterに本文を複製していないか |
| fallback | 近接ルールなしでも安全か | adapter未発動でも共通hard gateが残るか | adapter未発動でも共通hard gateが残るか |
| 実行可能性 | 利用可能なtoolで成果を完遂できるか | 固有機能なしでも代替経路があるか | 固有機能なしでも代替経路があるか |
| budget | rootと近接ルールが過密でないか | import後の常時量が過密でないか | alwaysApply ruleが増えすぎていないか |

PRには、3者への影響、追加した常時指示量、scoped化した内容、未確認の製品固有挙動を記録します。

## 9. 検証

`scripts/verify-ai-governance.sh` は最低限、次を検査します。

- ルート `AGENTS.md` の行数とbyte数。
- `CLAUDE.md` のimport契約。
- Claude CodeとCursorの必須adapterの存在と正本参照。
- 新しいSkillと近接ルールの存在。
- 廃止したreview収束条件とCursor禁止規則の残存。
- ソースコード変更の配送Skill発動、Issue必須、review、mergeability、merge等の別権限。
- 共通rootへのtool固有認証commandの再流入。
- UI Skillの上限と詳細正本への参照。

自動検査だけで、各toolの実際のrule発見挙動を完全に保証したとは扱いません。製品仕様が変わった時、adapterが発動しなかった時、同じルールが異なる意味で解釈された時は、この文書、adapter、検証scriptを同じ変更内で更新します。

## 10. 保守時の停止条件

次が残るハーネス変更は完了扱いにしません。

- 3エージェントのいずれかが共通hard gateへ到達できない。
- tool固有adapterだけに重要な判断基準が存在する。
- 同じhard gateが複数の正本で異なる文言・条件を持つ。
- root budgetを超えたまま、scoped化または機械化の検討がない。
- adapterのscopeが正本の対象と一致しない。
- 廃止した規則が検証scriptやtemplateから引き続き要求される。
- ソースコード変更が通常配送の途中で正常終了できる例外、またはreviewを自己レビューだけで代替できる規則が残る。
