# エージェントハーネス設計・保守ガイド

この文書は、Codex、Claude Code、Cursorで共有する、正本の読者・配置、委任、evidence、task-stateの最小契約です。説明文であり、機械検査や製品runtimeの代替ではありません。

## 正本、読者、責務

| 正本 | 主な読者 | 責務 |
|---|---|---|
| `AGENTS.md`、最寄りの`AGENTS.md` | 3製品 | hard gate、権限境界、path契約、最小実行 |
| `CLAUDE.md`、`.claude/rules/`、`.claude/skills/`、`.cursor/rules/` | Claude Code / Cursor | 正本へ到達する製品固有router |
| `.agents/skills/<name>/SKILL.md` | 3製品 | task固有の発動条件、手順、handoff |
| `docs/ai-governance/` | agent、reviewer | UI/UX、Issue、evidenceの判定基準 |
| この文書 | agent、reviewer、保守者 | source/readers、委任、evidence、task-state、runtime境界 |
| `scripts/validate_governance.py` | CI、保守者 | 形式、存在、参照、budgetのstatic検査 |

Codexはrootと最寄りの`AGENTS.md`、該当Skillを読みます。Claude Codeは`CLAUDE.md`からrootへimportし、path ruleとSkill adapterで同じ正本へ接続します。Cursorはrootと`alwaysApply: false`のMDC routerから接続します。adapterは本文を複製せず、失敗しても共通hard gateを弱めません。

## 読み分けと変更影響

- 全体の安全境界と権限はroot、path固有の契約は最寄りの`AGENTS.md`、task手順はSkillに置きます。
- 設計判断のheuristicは [`docs/agent-principles.md`](agent-principles.md)、ruleの追加・変更・削除基準は [`docs/ai-governance/13-maintenance-policy.md`](ai-governance/13-maintenance-policy.md)を読みます。
- logic、共有処理、API、型、data契約、複数layerを変える場合は、参照追跡または影響分析を入口にし、実code・契約・関連testで候補を確認します。利用できなければ理由を残して手動確認します。

## 配送stateとcheckpoint

改修配送は、次のcheckpointを順に通過します。各checkpointで対象HEAD / base、入力閉包、owner、終了条件を固定し、高コストgateへ進む前に次の入力を変えない状態を作ります。対象面ごとのgate選択は [`docs/ai-governance/03-evidence-and-completion-gates.md`](ai-governance/03-evidence-and-completion-gates.md)、実行手順（PR監視の詳細を含む）は GitHub配送Skillが所有します。

1. `implementation`: scope、acceptance、非対象、owner、変更pathを確定する。
2. `focused_verification`: 変更pathに対応する最小十分なtest・構造確認を実行し、未確認範囲を記録する。
3. `code_freeze`: source、test、設定、生成物を固定し、変更path・関連設定・生成物・条件からgateの入力閉包を確定する。
4. `measurement`: 固定したsnapshotと測定scopeでgate実行数、wall-clock、status照会数、出力bytesを記録する。
5. `publication_freeze`: Issue、PR、report、artifactの公開内容と安全性を固定する。
6. `external_gate`: 入力閉包が固定された状態で、必要なCI・review・thread確認を行う。
7. `review_fix`: actionableな修正をまとめ、交差するgateだけを再取得して再びfreezeする。
8. `accepted`: latest HEAD / base、CI、review、thread、mergeability、受入条件を同一snapshotで照合する。

高コストgate（full suite、coverage、外部CI、包括reviewなど）の開始条件は、`code_freeze`、測定scope、公開境界、再取得条件が確定していることです。gateの回数を固定せず、変更種別と既存gate mapで選びます。

## snapshot、evidence、delivery state

implementation・measurement・publicationのsnapshotは、HEAD / base、変更path、関連設定、生成物、実行条件へ束縛したstable evidenceです。CIのpending / success、review・threadの状態、mergeability、時刻、待機中のstatusはvolatile delivery stateとして別に記録し、stable evidenceの入力へ混ぜません。base、path、設定、生成物、条件が閉包と交差した場合だけ該当gateを失効し、base依存の外部gateはbase変更時に再取得します。thread解決だけではstable gateを失効させません。

gate ledgerは `gate / snapshot phase・HEAD・base / input paths / related config / generated artifacts / execution conditions / result / artifact reference` を持ち、失効時は `invalidation reason / reacquire scope` を追記します。判定不能時はskipせず、fallback理由と対象を残します。task-stateは現在状態、completion-gate reportは各gateの詳細台帳として分けます。

測定artifact自身が検証入力になる場合は、測定snapshotの後に行うreport annotationを測定scopeから外して別gateへ分離するか、明示した測定scopeへ固定します。annotation後のreportを同じ測定結果の入力として扱いません。token量は実telemetryを取得した場合だけ観測値とし、source-size estimateを格上げしません。

P0 / P1、security、secret、data integrity、受入証跡の矛盾は、コスト削減を理由に延期しません。P2-only findingと公開文言の調整は、既存のreview予算と限定された再確認条件に従い、不要な包括reviewへ拡張しません。

## 委任契約

委任は、他作業と重ならない専門riskをbounded laneへ分けるために使います。依頼時に `risk lane`、owner、target HEAD / base、target paths、受け入れ条件、`depends_on`、`snapshot_phase`、write ownership、runtime resources、ports、cleanup、`output_cap`、completion、verification、`reuse_evidence`、`invalidation_condition`を固定します。

同一PR・同一risk laneの監査は原則一回とし、completed laneはscope、結論、検証、未確認範囲、残るrisk、snapshot/diff、artifact参照を含む短いevidence packageだけを返します。

## task-state route

- Cross-session task-stateのfield sourceは [`docs/ai-governance/templates/task-state.json`](ai-governance/templates/task-state.json) だけとし、この文書はresumeの振る舞いだけを定めます。field名と型はtemplateから読みます。
- resume時は現在のsnapshotとclosureを確認し、条件が一致するcompleted evidenceをartifact referenceで再利用して、remaining workから開始します。完了済みの長い出力は再取得しません。
- timeoutは失敗・状態変化・evidence失効ではなく、laneは`running`のままbackoff付きで再待機します。
- laneや監視が終端`state`へ到達したrunでは、結果と停止理由を記録し、所有するresource・scheduled taskをcleanupして終了します。終端後の詳細照会は行いません。
- checkpointを逃した時だけ同じownerへ一度partial resultを求め、進展がなければscope shrink、縮小後も進展がなければreassignします。first failureだけでprimaryへ回収しません。
- `partial` / `unverified`は未確認範囲と再開条件を保持します。`complete`は受け入れ条件と必要gateを満たした場合だけ、`blocked`は権限・外部状態などの真の停止理由がある場合だけ使います。
- primaryが分離可能な作業を直接行う場合は、理由、subagent不能の証拠、scope shrink履歴、reassignment履歴、primary-only question、target paths、output capを記録します。

## evidenceと再利用

gate evidenceは、実際に読むinput paths、関連設定、生成物、実行条件、HEAD / base、結果、artifact参照を一つのinput closureへ束縛します。成功証拠はsnapshot、closure、条件が同じ場合だけ再利用し、変化したclosureだけを失効・再取得します。

task-stateはcross-sessionの現在状態、completed evidence packageは一回のlane結果の要約であり、別の記録です。`status=blocked`の停止理由はtask-stateの`risks_blockers.blockers`へ保持します。

completed packageは、status、scope / revision、verification、unperformed checks、remaining risks、stop reason、snapshot/diff、artifact referenceを分離します。raw logやfile全文を通常報告へ含めません。

## runtimeとadvisoryの境界

runtime/dev serverを使うlaneは、起動前にowner、PID、process group、port、readiness、cleanupを必須項目として計画し、起動後にPIDを記録します。成功、正常停止、失敗、割込みのいずれでもprocess groupを終了し、port解放を確認し、結果を記録します。owner、readiness、cleanupのいずれかが不明な実行は完了evidenceに使いません。runtimeを使わない場合もその旨を記録します。

`validate_governance.py`はstaticな形式・参照・budget検査です。製品version、rule発見、sandbox、権限、runtime routing、Hookのcontext注入やcontext pruningを保証しません。configured、observed、unverifiedを分け、static PASSをruntime成功と表現しません。

## budgetと完了

root、nested、adapter、canonical Skillの上限はvalidatorが検査します。source-sizeのestimateを製品のobserved token usageと混同しません。正本へ到達でき、adapterが本文を複製せず、重要linkとbudgetを満たし、実行済み検証と未確認範囲を報告できる状態を完了候補とします。失敗中の検証、未確認の重要条件、公開安全性または配送条件の問題は明記します。
