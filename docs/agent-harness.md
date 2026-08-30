# エージェントハーネス設計・保守ガイド

この文書は、Codex、Claude Code、Cursorで共有するエージェントルールの配置と、委任・証跡の最小契約を定めます。文面は人間向けの説明であり、機械検査の入力にはしません。

## 正本と接続

| 層 | 正本 | 役割 |
|---|---|---|
| 共通核 | `AGENTS.md`、`CLAUDE.md` | 全作業の安全境界と入口 |
| path固有 | 最寄りの`AGENTS.md` | frontend、backend、operationsの契約 |
| task固有 | `.agents/skills/<name>/SKILL.md` | 作業種類ごとの手順 |
| 詳細基準 | `docs/ai-governance/` | UI/UX、Issue、証跡の判定 |
| adapter | `.claude/`、`.cursor/` | 正本へ接続する短い製品固有設定 |
| 機械検査 | `scripts/validate_governance.py` | 形式、参照、budget、重要リンク |

`CLAUDE.md`は`@AGENTS.md`だけをimportします。Claude CodeとCursorのadapterは適用範囲と読む正本だけを示し、共通契約を複製しません。task SkillはCodex、Claude Code、Cursorで同じ`.agents/skills/`を正本にします。

自動判定できる形式、存在、参照、上限は`validate_governance.py`へ置きます。判断が必要な品質基準は正本に短く書き、製品固有のruntime挙動やtoken telemetryをrepositoryの検査で代用しません。

## 変更の進め方

目的、受け入れ条件、非対象、現在のHEADとbase、変更path、検証方法を先に確認します。影響範囲が明らかに局所的でないコード変更は、利用可能な影響分析または参照追跡を入口にします。取得できない場合は理由を残して実コード、契約、関連testへフォールバックします。

実装、検証、文書更新を完了し、実施していない確認と残るriskを分けて報告します。ソースコード変更はGitHub配送SkillのIssue、branch、commit、PR、CI、review、mergeability契約に従います。merge、close、release、deploy、破壊的操作には対象を特定した別の明示指示が必要です。

### 変更影響調査の入口

ロジック、共有処理、API、型、データ契約、複数レイヤーを変える場合は、利用可能な影響分析または参照追跡を使い、実コード・契約・関連testで候補を確認します。分析が使えない場合は理由を記録し、同じ確認を手動で行います。

## 委任契約

委任は、他作業と重ならない専門riskをbounded laneへ分けるために使います。委任時に次を固定します。

- risk lane、owner、target HEAD / base、target paths、受け入れ条件
- `depends_on`、`snapshot_phase`、write ownership、runtime resources、ports、cleanup
- `output_cap`、completion、verification、`reuse_evidence`、`invalidation_condition`

同一PR・同一risk laneの監査は原則一回とし、同じ状態の結果を根拠なく再取得しません。completed laneはscope、結論、検証、未確認範囲、残るrisk、snapshotまたはdiff、artifact参照を含む短いevidence packageだけを返します。

進展のないlaneでは固定timeout回数で失敗判定しません。checkpoint前のtimeoutは状態変化とみなさず、通知またはbackoff付きre-waitでownerを維持します。checkpointを逃した時だけ、同じownerへ一度boundedなpartial resultを求めます。継続が不明ならscopeを縮小し、縮小後も進展がなければ再割当します。first failureだけでprimaryへ回収しません。

分離可能な作業をprimaryが直接行う場合は、次の7項目だけを記録します。

`specific_reason`、`evidence_subagent_cannot_continue`、`scope_shrink_history`、`reassignment_history`、`primary_only_question`、`target_paths`、`output_cap`

## 証跡と再利用

gateのevidenceは、実際に読む`input paths`、関連設定、生成物、実行条件、HEAD / base、結果、artifact参照を一つのinput closureへ束縛します。成功した証拠は、snapshot、closure、条件が同じなら再利用できます。snapshotが異なる場合はsourceとtarget、間のdiffがclosureに交差しないこと、baseと条件が不変であることを確認します。

closureを構成するpath、設定、生成物、条件、base依存が変わったgateだけを失効させ、理由と再取得範囲を記録します。HEADが変わっただけで全gateを一括失効させません。長時間検証はexit code、pass / fail / skip、coverage総計、warning、失敗箇所、artifact参照に絞り、raw logやfile全文を通常の報告へ含めません。

## runtime resource

runtimeまたはdev serverを使うlaneは、起動前にowner、PID、process group、port、readiness確認、cleanup責任を固定します。終了・停止・失敗時にprocess groupの終了とport解放を確認し、証跡へ残します。owner不明、port衝突、readiness未確認、cleanup未確認の実行は完了根拠にしません。runtimeを使わない場合は、使用しなかったことだけを記録します。

## instruction budgetとSkill Evaluation

root、nested rule、adapter、Skillの上限とroot + nested `AGENTS.md`の合計上限は`validate_governance.py`が検査します。計測値はsource-sizeのestimateであり、製品のobserved usageではありません。Skill Evaluationはfrontmatter、trigger、参照、責務重複、budget、syntheticな代表設定をstaticに確認します。認証、費用、隔離workspace、外部runnerが確定しないlive benchmarkは実行せず、static結果をlive成功と表現しません。

## 完了条件

正本へ到達でき、adapterが本文を複製せず、重要リンクが解決し、budgetを満たし、実行した検証と未確認範囲が報告されている状態を完了候補とします。検証失敗、未確認の重要条件、公開安全性の問題、未解決の配送条件がある場合は、その状態を明記します。

各製品のversion、rule発見、sandbox、権限、runtime routing、context pruningはrepositoryの静的検査だけでは保証できません。製品固有の差は、製品名、version、実行形態、再現pathを分けて記録します。
