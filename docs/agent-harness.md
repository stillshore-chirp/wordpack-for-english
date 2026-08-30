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

## 委任契約

委任は、他作業と重ならない専門riskをbounded laneへ分けるために使います。依頼時に `risk lane`、owner、target HEAD / base、target paths、受け入れ条件、`depends_on`、`snapshot_phase`、write ownership、runtime resources、ports、cleanup、`output_cap`、completion、verification、`reuse_evidence`、`invalidation_condition`を固定します。

同一PR・同一risk laneの監査は原則一回とし、completed laneはscope、結論、検証、未確認範囲、残るrisk、snapshot/diff、artifact参照を含む短いevidence packageだけを返します。

## task-state route

- Cross-session task-stateのfield sourceは [`docs/ai-governance/templates/task-state.json`](ai-governance/templates/task-state.json) だけとし、この文書はresumeの振る舞いだけを定めます。field名と型はtemplateから読みます。
- resume時は現在のsnapshotとclosureを確認し、条件が一致するcompleted evidenceをartifact referenceで再利用して、remaining workから開始します。完了済みの長い出力は再取得しません。
- timeoutは失敗・状態変化・evidence失効ではなく、laneは`running`のままbackoff付きで再待機します。
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
