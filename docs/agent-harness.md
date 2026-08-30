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

### 変更影響調査の入口

ロジック変更、共通処理変更、API・型・データ契約変更、複数レイヤーのリファクタリングなど、影響範囲を局所的と断定できない非自明なコード改修は、実装前の影響範囲調査で利用可能な `code-review-graph` を標準的な入口として使う。これは特定製品のコマンドや設定を共有契約に固定するものではなく、利用可能なgraphの変更影響・依存関係結果を取得する能力を指す。

graph結果を起点に、変更対象に関係するコード、呼び出し元、レイヤー境界・契約境界、テスト候補を絞り込み、得られた候補を実コード、契約、関連テストで確認する。graphだけで影響範囲、安全性、テスト十分性を確定したり、レビュー・検証を省略したりしない。動的参照、設定依存、生成物、実行時結合など、graphに現れない可能性のある関係は通常の確認対象として残す。

文書のみ、文言のみ、独立した局所CSSのみで、ロジック、公開契約、共有primitive、global style、呼び出し関係に影響しないと変更者が確認できる場合はgraphを省略できる。これらを組み合わせた変更、または局所性を断定できない変更は標準入口へ戻す。

graphが利用不能、未設定、古い、解析失敗、情報不足、または結果が空／信頼できない場合は、理由を記録して `rg`、import追跡、参照追跡、実コード・契約・関連テスト確認へフォールバックする。フォールバックはgraph利用時と同じ影響範囲確認と最小十分な検証を満たし、GitHub配送とレビュー収束の条件を変更しない。graphの状態やfallback理由は、必要な範囲で変更影響の証跡へ残す。

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

CI watcherとread-only照会の配送順序は [GitHub配送Skill](../.agents/skills/github-delivery/SKILL.md) が所有します。この節は、取得手順を複製せず、収束判断と証拠の保持範囲だけを定めます。

primaryが継続保持するcontrol-plane ledgerは、goal、acceptance、非対象、HEAD / base、changed paths、commit責務、completion-gate summary、CI / review / thread / mergeability、権限、riskだけです。raw log、file全文、PR本文全文、解決済みthread全文は台帳や委任報告へ入れず、必要な場合だけ参照へ退避します。旧HEADはcommit、finding、fix commit、invalidation reasonだけを残します。

- latest meaningful changeのCI・review・thread・mergeabilityは、配送Skillが定める最新snapshotで確認し、台帳には状態の要約と取得時点だけを残す。同一snapshot・input closure・execution conditionsなら既存証拠をそのまま再利用し、snapshotが異なる場合はsource snapshotとtarget snapshotを記録し、between-diffがinput closureと交差せず、baseとexecution conditionsが不変であることを確認できる場合に限り再利用する。
- timeoutは状態変化や証拠失効を意味しない。timeout後は通知またはbackoff付きre-waitを優先し、状態照会は`new signal`または具体的な`diagnostic reason`がある場合だけ行う。
- 完了したlaneの長文結果を再取得しない。`artifact_reference` fieldを含むbounded evidence packageを使い、必要な詳細は限定された参照先から一度だけ取得する。
- 同一PR・同一HEAD系列の包括レビューは、初回レビュー1回と指摘修正後の再レビュー1回までを原則とする。レビューcomment、thread、指摘の件数ではなく、同じ配送系列のreview実行回数で数える。
- 3回目以降は、P0 / P1、security・secret・data integrity、または現在の受入証跡が誤りと分かる具体的な矛盾だけを許可し、新しい変更範囲・risk laneや抽象的な`evidence gap`だけでは例外にしない。許可前に対象gate、無効になる証跡、severity、未修正時の具体的な影響を記録する。
- P2以下だけが残る場合は、影響とnon-blocking判断を記録し、必要なら別Issueへ分離して包括レビューを終了する。P2-only（hard-riskまたは現在の受入証跡が誤りと分かる具体的な矛盾がない場合）は`action=track`をterminalとし、`follow_up_reference`を必須にする。`action=fix`、`action=re_review`、追加の包括reviewは拒否する。成功済みreviewやfull gateを再実行する場合も、失効理由と対象範囲を台帳へ記録する。
- 変更path、修正commit、元の指摘、focused test結果だけを再レビューの文脈にする。変更のないheadでclean reviewを追加せず、reviewが提供されない場合は未確認範囲とblockerを報告する。
- actionableな未解決threadがなく、GitHubのmergeabilityがcleanであることを確認する。mergeまたはcloseは別の明示指示がある場合だけ行う。

### Focused review terminal

focused reviewは開始時に`reviewed_paths`と確認する`questions`を固定し、P0 / P1、security、secret、data integrity、現在の受入証跡が誤りと分かる具体的な矛盾を確認します。指定scopeを完了した時点でterminalにでき、P2-onlyは`action=track`としてterminalにします。一般的な改善探索やcomprehensive scopeへの拡張はfocused reviewでは禁止します。

focused reviewのterminal evidenceは`reviewed_paths`、`finding_severity`、`unverified_scope`、`remaining_risk`、`artifact_reference`の5 fieldだけに限定し、long resultを含めません。focused review terminalを確定する前にfull gateをfinalizeせず、同一closure・conditionsの成功証跡はreuseします。

### Review decision record

既存`review` eventは、既存のstatus、head、latest head、actionable thread、mergeabilityを保持したまま、boundedな`decision_record` objectを含めます。decision recordのfieldは次の6つだけです。`review_round`は同一delivery系列の包括reviewの序数とし、focused reviewはそのround内のterminal確認として扱います。`scope`（focused / comprehensive）と`terminal`はevent metadataであり、decision recordのfieldには数えません。

| Field | Meaning |
|---|---|
| `review_round` | 1から始まる同一delivery系列の包括review round。2回目は指摘修正後の再review、3回目以降は許可された例外だけ。 |
| `highest_severity` | `none`、`P2`、`P1`、`P0`の最高severity。security、secret、data integrity、具体的な受入証跡の矛盾は`exception_reason`のcategoryで明示し、P2-onlyへ隠さない。 |
| `action` | `pass`、`track`、`fix`、`re_review`、`blocked`の判定。`track`はP2-onlyのterminal、`fix` / `re_review`はP0 / P1または許可例外だけで使う。 |
| `exception_reason` | 通常は空。round 3以降の例外では、category、target gate、具体的なdetail、`impact_if_unfixed`を持つbounded recordとし、`evidence gap`単独を拒否する。 |
| `invalidated_evidence` | 例外または修正で無効になる対象gateのevidence key / reference列。例外を許可する前に対象範囲を確定する。 |
| `follow_up_reference` | `track`、`fix`、`re_review`に結び付く公開安全なIssue、commit、review、gate等の参照。P2-onlyの`track`では必須。 |

`highest_severity=P2`でhard-riskと具体的な証跡矛盾がない場合だけP2-onlyと判定し、`track`をterminalにします。`pass`でP2を隠したり、P2を理由に`fix` / `re_review`や追加包括reviewへ進めたりしません。round 3以降の例外は、`exception_reason`、非空の`invalidated_evidence`、`highest_severity`、`impact_if_unfixed`をactionの前に揃えます。

同じevent streamの`review`でfocused reviewのterminal（converged）を確定してから、後続の`full_gate` finalizationを1回だけ許可します。terminal前のfull gate、高コストgateの先行実行、terminal後の同一full gateの追加実行は拒否します。同一input closure・execution conditionsで成功したgateは既存evidenceをreuseし、P2 trackだけでは再取得しません。input closureまたは条件が失効した場合だけ、既存のinvalidation ruleに従って再取得します。

このdecision recordとstate transitionはrepository required verifierでhard gateとして検査可能にします。Codex app-onlyのUI/API enforcementはアプリ層の責務であり、共有正本やrepository verifierがその実装を擬似実装・runtime証拠化しません。roleを識別できないHookは既存どおりadvisory・fail-openとします。

### Gate evidence ledger

gate evidenceは、次のcompact ledgerで入力閉包とsnapshotへ束縛します。

| gate | input paths | related config | generated artifacts | execution conditions | snapshot / result / evidence package | invalidation reason / reacquisition target |
|---|---|---|---|---|---|---|
| gateごと | 対象pathと依存path | 関連設定・schema | 生成物とchecksum | runtime、base依存、実行条件 | HEAD / base、pass・fail・skip、evidence package内の`artifact_reference` field | 失効理由と再取得対象 |

input closureは、gateが実際に読む対象path、関連設定、生成物、実行条件、必要なbase依存の集合です。証拠にはこの閉包、snapshot、result、`artifact_reference` fieldを含むevidence packageを記録します。`reuse_evidence`は、同一snapshot・input closure・execution conditionsならそのまま再利用し、snapshotが異なる場合はsource snapshotとtarget snapshot、between-diffがinput closureと交差しないこと、baseとexecution conditionsが不変であることを記録して再利用します。HEADが変わっただけでは全gateを失効させず、閉包を構成するpath・設定・生成物・条件・base依存が変わったgateだけを失効させ、`invalidation_condition`、理由、再取得対象をledgerへ記録します。閉包が不変であるgateは、target snapshotへ影響しない根拠を残して再利用できます。

長時間検証のevidence packageは、exit code、pass / fail / skip、coverage総計、warning要約、failure箇所、artifact参照（evidence package内の artifact_reference field）だけにします。成功時はfile別coverageと反復進捗を渡さず、raw outputは必要な場合だけ参照へ置きます。
<!-- agent-harness:review-convergence:end -->

## Subagent orchestration
<!-- agent-harness:subagent-orchestration:start -->

<!-- agent-harness:subagent-orchestration-contract:01 -->

<!-- agent-harness:subagent-orchestration-contract:02 -->

<!-- agent-harness:subagent-orchestration-contract:03 -->

<!-- agent-harness:subagent-orchestration-contract:04 -->

<!-- agent-harness:subagent-orchestration-contract:05 -->

<!-- agent-harness:subagent-orchestration-contract:06 -->

<!-- agent-harness:subagent-orchestration-contract:07 -->

サブエージェントは、同じ証拠を読む担当を増やすためではなく、専門riskを独立したbounded laneへ分けるために使います。探索、実装、focused verification、review、review fix、docsは、分離可能ならsubagent-default（subagent-first）で委任します。単一API、CI watcher、read-only照会、短いthread返信、短い競合解消などhandoffの固定費が見合わない作業はprimaryが担当します。

委任前に、他作業と重複しないrisk lane、target HEAD / base、target path、確認する具体的な問い、acceptanceを委任の最低文脈として定義し、target pathsは単一pathでも対象集合として明示します。既存報告やprimaryの一次証拠で不足する理由、write ownership、`depends_on`、`snapshot_phase`、runtime_resources、ports、cleanup、output_cap、completion、verification、`reuse_evidence`、`invalidation_condition`、`artifact_reference`も定義し、従来の委任記録にあるwrite ownership、completion、verification、invalidation conditionを維持します。同一PRの各laneは一人のownerが開始からcompletionまで担当し、同一HEAD・同一risk laneの監査は原則1回です。包括監査を複数agentへ同時委任せず、対象変更、新しい実行証拠、明確な証拠不足・矛盾がある場合だけ再監査します。委任文脈では製品固有のtool、UI、runtime configを共有契約へ持ち込みません。委任判断の説明ではspecific reason、context-vs-workを補助的に示してもよいが、direct-primary exceptionのfieldには含めません。

分離可能な仕事をprimaryが直接行うのはdirect-primary exceptionに限ります。例外の記録は、`specific_reason`、`evidence_subagent_cannot_continue`、`scope_shrink_history`、`reassignment_history`、`primary_only_question`、`target_paths`、`output_cap`の7 fieldだけを持ちます。受入・統合・配送判断はprimaryの固有責務で、監査の矛盾は一次証拠で解決します。

subagent evidence packageは、scope / acceptance、changed paths、conclusion、verification results、unperformed checks、remaining risks、`snapshot_phase`、snapshotまたはdiff identifier、input closure、execution conditions、`artifact_reference` fieldを含む必要最小限として返します。raw log、file全文、full historyは必須にせず、必要な詳細は参照へ置きます。primaryの最終受入はこのpackageを根拠にし、full fileやfull logを要求しません。

進捗がなく同じ結果を反復するlaneは、固定timeout回数ではなくlogical `checkpoint` eventでdeterministicに判定し、`checkpoint miss → partial result（同じownerへ1回） → no progress / continuation unknownならscope shrink → 縮小scope後もno progressならreassign` の順で進めます。timeoutがcheckpoint前に発生した場合は状態変化やstallとみなさず、backoff付きre-waitを優先し、status-listを取得せずownerを維持します。partialに進展があれば`progress_revision`を更新し、次のcheckpointとownerを維持します。first agent failure alone はdirect-primary exceptionの理由にならず、partial resultと未確認範囲を返してから縮小scopeでも進展がない場合だけownerを再割当します。completionに定めた停止・scope縮小・primary返却条件に従い、invalidation conditionが成立した場合だけ再開します。completed laneはcompact terminal receiptとartifactだけを返し、long resultを再取得しません。固定timeout countだけでstallまたはfailureを判定しません。

| Field | Meaning |
|---|---|
| risk lane | 重複しない確認責務 |
| owner | agentまたはメインエージェント |
| target HEAD / base | 委任時点で確認対象とするcommitとbase |
| target path | 調査・変更・検証の対象path |
| depends_on | 先行laneまたは必要evidenceのreference。循環依存は許可しない |
| snapshot_phase | `implementation`、`provisional`、`review`、`final`など、証跡を取得した段階。provisionalをfinalの根拠へ昇格しない |
| write ownership | laneが編集・生成・公開できるpathと操作の境界 |
| runtime_resources | laneが使用する一時runtime resource、そのowner、用途、解放条件 |
| ports | laneが占有するport claim、そのowner、解放条件 |
| cleanup | 完了・停止・失敗時の後始末、owner、完了条件 |
| output_cap | handoffへ返す出力の上限と単位。raw logの全文化を許可しない |
| completion | laneの完了条件と、進捗がない場合の停止・scope縮小・primaryへの返却条件 |
| verification | 実行する検証と、compactな結果の証跡 |
| verified snapshot | clean commit、またはbase HEADと確認済みdiffの識別子 |
| status | pending / active / passed / finding / blocked |
| progress_revision | logical checkpoint eventで更新する進捗revision。timeout countやcommentaryだけでは更新しない |
| checkpoint_condition | 進捗またはterminalを確定するdeterministicなcheckpoint条件 |
| expected_next_signal | 次のcheckpointまでに期待する具体的な進捗・完了signal |
| partial_result_cap | checkpoint miss時に同じownerへ一度だけ求めるbounded receipt。findings有無、unverified_scope、remaining_work、terminal_possible、artifact_referenceだけを含む |
| on_checkpoint_miss | timeout前後のre-wait、status-list抑止、owner維持、partial要求の順序 |
| scope_shrink_condition | revision不変で進展または継続が不明な場合に縮小するscopeと停止条件 |
| reassignment_condition | 縮小scopeでも進展がない場合だけownerを再割当する条件 |
| terminal_reason | completed、blocked、scope完了などをcompact terminal receiptへ記録する理由 |
| reuse_evidence | 同一snapshot・input closure・execution conditionsならそのまま再利用。snapshotが異なる場合はsource snapshotとtarget snapshot、between-diffがinput closureと交差しないこと、baseとexecution conditionsが不変であることを確認した成功証跡へのreference |
| invalidation_condition | 再検証が必要になる対象変更または新証拠、失効理由、再取得範囲 |
| artifact_reference | evidence package内のfield。bounded evidence packageまたは必要時のartifactを指す公開安全なreference |
| evidence package | scope / acceptance、changed paths、conclusion、verification results、unperformed checks、remaining risks、snapshotまたはdiff identifier |
| evidence package extensions | `snapshot_phase`、input closure、execution conditions、evidence package内の`artifact_reference` field |
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
9. 開発中とreview修正中は変更pathに対応するfocused testを実行した。
10. 最終HEADで変更範囲に必要な包含関係上の最上位full gateをそれぞれ1回実行し、gate evidenceの入力閉包・snapshot・失効理由を台帳へ残し、同じsnapshotで内包gateを別途実行していない。

## 既知の限界

各製品のversion、Remote SSH、sandbox、権限、Skill discoveryの実装差まではリポジトリ内の静的検証だけで保証できません。adapterと正本の構造をCIで固定し、実環境で発見できない場合は製品名、version、実行形態、再現パスをIssueへ残します。アプリ内部のautomatic routing、token使用量、context pruningは共有契約から検証不能です。
