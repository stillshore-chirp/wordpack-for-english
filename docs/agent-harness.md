# エージェントハーネス設計・保守ガイド

この文書は、WordPack for English を Codex・Claude Code・Cursor のいずれで扱っても、同じ品質基準を過不足なく適用するための構成を定義する正本です。

## 目的

エージェント向け指示は、増やすほど安全になるとは限りません。常時読み込まれる長文、同じ規則の複数正本、タスクと無関係な手順は、重要な指示への注意を薄め、過剰実装や見落としを増やします。

このリポジトリでは、品質基準を次の4層へ分けます。

| 層 | 役割 | 主な配置 |
|---|---|---|
| 常時読込の共通核 | 全作業で必要な安全境界、証跡、基本進行 | `AGENTS.md`, `CLAUDE.md` |
| path固有ルール | frontend、backend、operationsなど領域固有の契約 | nested `AGENTS.md`, `.claude/rules/`, `.cursor/rules/` |
| task固有ワークフロー | UIレビュー、GitHub配送、本番調査、公開安全性 | `.agents/skills/`, `.claude/skills/` |
| 機械検証 | 形式、参照、instruction budget、禁止された重複 | `scripts/verify-agent-harness.sh`, CI |

## 正本とアダプター

- 共有ルールの原点はルート `AGENTS.md`。
- 領域固有ルールの正本は、対象ディレクトリに最も近い `AGENTS.md`。
- task固有手順の正本は `.agents/skills/<name>/SKILL.md`。
- UI/UXの詳細判定基準は `docs/ai-governance/`。
- `.claude/rules/`、`.claude/skills/`、`.cursor/rules/` は、正本を各製品の読込機構へ接続する薄いアダプター。
- アダプターへ正本の本文をコピーしない。対象ファイルと読むべき正本だけを示す。

## 3製品の接続方法

### Codex

- ルートから現在の作業ディレクトリまでの `AGENTS.md` を階層的に利用する。
- ルートから複数領域を編集する場合も、変更対象に最も近い `AGENTS.md` を明示的に確認する。
- `tests/`、root文書、`.github/workflows/`、deploy scriptなど、祖先pathだけでは領域正本へ到達しない対象は、ルート `AGENTS.md` のpath bridgeから追加正本を読む。
- task固有手順は `.agents/skills/` から読む。

公式資料: [CodexのAGENTS.md](https://developers.openai.com/codex/guides/agents-md)

### Claude Code

- `CLAUDE.md` は `@AGENTS.md` だけをimportし、共通核を一重に共有する。
- `.claude/rules/*.md` の `paths` で、領域固有の正本を必要な時だけ案内する。
- `.claude/skills/<name>/SKILL.md` は、対応する `.agents/skills/` を読む薄いadapterにする。
- `@` importで長文を分割しても常時読込量は減らないため、task手順はSkillへ置く。

公式資料: [Claude Codeのメモリとrules](https://code.claude.com/docs/ja/memory)、[Claude CodeのSkills](https://code.claude.com/docs/ja/skills)

### Cursor

- 共通核はルート `AGENTS.md` から読む。
- `.cursor/rules/*.mdc` の `globs` と `alwaysApply: false` でpath固有の正本を案内する。
- task固有手順はAgent Skills互換の `.agents/skills/` を正本として使う。
- `.cursor/rules/` に長い共通ルールを再掲しない。

公式資料: [Cursor Rules](https://docs.cursor.com/context/rules)、[Cursor Agent Skillsの導入](https://cursor.com/changelog/2-4)

## ルール配置の判断

新しい規則を追加する前に、次の順で判断します。

1. 全タスクで毎回必要か。
   - 必要: ルート `AGENTS.md`。
   - 不要: 次へ。
2. 特定のパスだけに必要か。
   - 必要: 最寄りのnested `AGENTS.md`。Claude/Cursorには薄いpath adapterを追加する。
   - 不要: 次へ。
3. 特定の作業種類だけに必要か。
   - 必要: `.agents/skills/`。Claudeには薄いSkill adapterを追加する。
   - 不要: 次へ。
4. 自動判定できるか。
   - できる: script、test、lint、CIへ置く。
   - できない: 人間とエージェントが判断できる短いheuristicとして文書化する。
5. 既存の正本へ統合できるか。
   - できる場合は新規文書を増やさず、既存正本を更新する。

## Hard gateとheuristic

### Hard gate

違反時に作業を停止または未完了扱いにする、客観的に判定可能な条件です。

例:

- secretや個人情報を公開しない
- 未実施検証を成功扱いしない
- P0を残してUI/UX完了としない
- 最新headの必須CIが失敗中ならマージ可能と報告しない
- merge、close、破壊的操作は明示された権限内だけで行う

### Heuristic

複数の目的が競合する場面で、設計判断を助ける目安です。

例:

- DRY、KISS、SRP、OCP、YAGNI
- 関数・ファイルの大きさ
- 抽象化する重複回数
- Unit / Integration / E2Eの配分
- コメント量

heuristicを「常に」「必ず」と書く場合は、例外が成立しない理由を示します。数値だけをPass / Failへ変換しません。

## ソースコード変更のGitHub配送権限

ユーザーがソースコードの追加・変更・削除を依頼した時点で、変更規模にかかわらず `.agents/skills/github-delivery/SKILL.md` を発動します。ここでいうソースコードには、製品コードだけでなくtest、script、workflow、schema、挙動を変える設定を含みます。read-onlyの調査・相談は含みません。

権限を次の2種類へ分離し、「pushやPRには追加確認が必要だがmergeも同じ権限でよい」といった誤解を防ぎます。

| 区分 | ソースコード変更依頼に含まれる操作 |
|---|---|
| 通常配送 | 主Issueの検索・作成・更新、専用branch、commit、push、非ドラフトPR、CI確認・再実行、コードレビュー対応、review threadへの返信・解決、mergeability確認 |
| 別の明示指示が必要 | merge、Issue / PRのclose、release、production deploy、破壊的操作 |

通常配送は、作業開始時に包括的な再許可を求めず、GitHub上でマージ可能な状態になるまで続けます。完了判定は [`docs/ai-governance/03-evidence-and-completion-gates.md`](ai-governance/03-evidence-and-completion-gates.md)、実行順序はGitHub配送Skillを正本とします。GitHub上で確認可能なコードレビューが得られない場合、自己レビューだけで代替せず未完了blockerとして報告します。

## Instruction budget

次をhard upper boundとします。短いほど常に良いという意味ではなく、超過時に構造を見直すための上限です。

| 対象 | 行数 | UTF-8 bytes |
|---|---:|---:|
| ルート `AGENTS.md` | 180以下 | 16 KiB以下 |
| nested `AGENTS.md` | 100以下 | 8 KiB以下 |
| `.claude/rules/` / `.cursor/rules/` adapter | 30以下 | 4 KiB以下 |
| `.claude/skills/` adapter | 30以下 | 4 KiB以下 |
| canonical Skill | 180以下 | 16 KiB以下 |
| ルート + 1つのnested `AGENTS.md` | - | 24 KiB以下 |

超過を正当化する場合は、常時読込でなければならない理由、分割できない理由、3製品への影響をIssueとPRへ記録し、検証scriptの上限を黙って緩和しません。

## 禁止する構造

- tool別ファイルへ同じ長文を複製する
- `AGENTS.md`、Skill、詳細docsで同じchecklistをそれぞれ正本化する
- GitHub CLIなど一つのclientだけを、同等clientが使える状況でも必須化する
- Codex固有のreview名やbranch prefixを、Claude CodeとCursorにも共通の完了条件として課す
- 変更のない同一headに対して、clean結果を得るためだけにレビューを反復する
- read-onlyの回答へIssue / branch / PR欄の定型出力を要求する
- path scopeで解決できる規則を常時読込へ戻す
- 形式で検査できる条件を自然言語だけで維持する

## GitHub reviewの収束
<!-- agent-harness:review-convergence:start -->

- latest meaningful changeに対して対象branchで定義されたpush / pull_request等のCIと、GitHub上で確認可能な自動または人間のコードレビューを確認する。
- 同一PR・同一HEAD系列の包括レビューは、配送対象の最終HEADに対する初回レビュー1回と、指摘修正後の再レビュー1回までを原則とする。修正によるHEAD更新を含む同じ配送系列への包括レビュー実行回数で数え、review comment、thread、指摘の件数では数えない。
- 3回目以降の包括レビューは実行しません。次のいずれかで前回証拠が失効した場合だけ、対象risk laneと変更pathを明示した限定再確認を行う。
  - 未解決のP0またはP1がある。
  - セキュリティ、秘密情報、データ整合性に関わる未解決事項がある。
  - 前回レビュー後に新しい変更範囲またはrisk laneが追加された。
  - 前回のレビュー証拠に具体的な不足または矛盾が見つかった。
- P2以下の指摘だけが残る場合は、影響とnon-blocking判断をPRへ記録し、必要なら別Issueへ分離して同じPRの包括レビュー周回を終了する。
- 再レビューまたは限定再確認ではfull historyを渡さず、修正commit、変更path、元の指摘、focused test結果だけを文脈として使う。
- 成功済みレビューまたはfull gateを再実行する場合は、対象変更、新規risk lane、実行条件変更、証拠期限切れなど、証拠が失効した具体的な理由を記録する。
- メインエージェントはPRごとにHEAD系列、包括レビュー実行回数、確認済みsnapshot、結果、証拠の失効理由を記録する。
- 変更のないheadで追加のclean reviewを集めない。
- ソースコード変更でreviewが提供されない環境では、自己レビューを完了条件の代替にせず、未確認範囲とblockerを報告する。
- actionableな未解決threadがなく、GitHubのmergeabilityがcleanであることを確認する。
- mergeまたはcloseは別の明示指示がある場合だけ行う。
<!-- agent-harness:review-convergence:end -->

## Subagent orchestration
<!-- agent-harness:subagent-orchestration:start -->

サブエージェントは専門riskを独立して並列化するために使い、同じ証拠を読む担当を増やすために使いません。メインエージェントは委任前に、次を満たす重複しないlaneを定義します。

- そのagentだけが担当するrisk lane。
- 対象HEAD、対象path、確認する具体的な問い。
- 既存報告やメインエージェント自身の一次証拠確認では不足する理由。

この3点を定義できない委任は行いません。包括監査を複数agentへ同時委任せず、同一HEAD・同一risk laneの独立監査は原則1回とします。再監査を認めるのは、対象コードが変わった、新しい実行証拠が得られた、前回監査に明確な不足がある、または未解決の証拠矛盾がある場合です。修正後に変更pathを対象再検証することと、未変更HEADへ同じ監査を繰り返すことを区別します。

監査結果が矛盾した場合は追加agentの多数決を取りません。メインエージェントがsource code、test設定、実際のcommand結果、commit hashなどの一次証拠を確認して解決します。

委任時はfull-history forkを既定にしません。必要なHEAD、path、acceptance、既知の指摘だけを短く渡します。報告は変更path、P0 / P1、実行結果、未実行項目と残るriskを中心に簡潔にします。

検証は次の段階を守ります。

1. 開発中は変更によって影響を受けるfocused testを先に実行する。
2. 配送対象の最終HEADが確定した時点でfrontend / backend / operationsなど必要なfull gateを原則1回実行する。
3. 成功済み検証を再実行する時は、対象変更、生成物変更、実行条件変更、証拠期限切れなど、証拠が失効した理由を記録する。

メインエージェントは次のrisk lane台帳を保ち、担当scopeと結果を統合して重複を止めます。clean commitを確認した場合はcommit SHAを記録します。未commitの共有worktreeを確認した場合は、base HEADに加えて、確認したpathとdiffを一意に識別できる値を記録し、HEADだけを監査済みsnapshotとして扱いません。

| Field | Meaning |
|---|---|
| risk lane | 重複しない確認責務 |
| owner | agentまたはメインエージェント |
| verified snapshot | clean commit、またはbase HEADと確認済みdiffの識別子 |
| status | pending / active / passed / finding / blocked |
| invalidation condition | 再検証が必要になる対象変更または新証拠 |
<!-- agent-harness:subagent-orchestration:end -->

## ルール変更時の確認

1. 変更を `common / path / task / machine` のどこへ置くか決めた。
2. Codexのroot / nested `AGENTS.md`で必要なルールへ到達できる。
3. Claude Codeの`CLAUDE.md`、path rule、Skill adapterで必要時だけ到達できる。
4. Cursorの`AGENTS.md`、MDC rule、Agent Skillで必要時だけ到達できる。
5. adapterは正本を参照するだけで、長文を複製していない。
6. hard gateとheuristicを区別した。
7. instruction budgetを満たした。
8. 旧正本、循環参照、壊れたリンクを残していない。
9. `bash scripts/verify-agent-harness.sh`を実行した。
10. UI/UXガバナンスを変えた場合は`bash scripts/verify-ai-governance.sh`も実行した。

## 既知の限界

各製品のversion、Remote SSH、sandbox、権限、Skill discoveryの実装差まではリポジトリ内の静的検証だけで保証できません。adapterと正本の構造をCIで固定し、実環境で発見できない場合は製品名、version、実行形態、再現パスをIssueへ残します。
