# Issue #643 エージェントガバナンス縮約監査

## Scope とスナップショット

対象は、共有入口、path/task router、canonical Skill、保守正本、静的検査およびCI接続です。比較は変更前 `e96d0fd` と変更後 `5500b0b` に固定しました。4つのcanonical sourceは `AGENTS.md`、`docs/agent-principles.md`、`docs/agent-harness.md`、`docs/ai-governance/13-maintenance-policy.md` です。

行・byteはsource-sizeの測定値、tokenは `ceil(unicode_codepoints/4)` によるestimateです。製品のtokenizer、Hook注入量、observed usageは測定していません。

## Source inventory

| source group | reader / owner / applicability / enforcement | 現行budget（source lines / bytes） | 主な分類 |
|---|---|---|---|
| root/nested `AGENTS.md`、`CLAUDE.md` | Codex・Claude Code・Cursor / repository / 全体・backend・frontend・operations / loaderとstatic validator | 5 sources / 158 / 11,180B | hard gate、authorization、routing、minimal procedure |
| canonical 7 Skills: application-security、data-analysis、github-delivery、production-investigation、security-publication、skill-evaluation、ui-ux-review | 3製品 / repository / task trigger時 / frontmatter・budget・linkをvalidatorが検査 | 7 / 533 / 41,251B | task procedure、scope別hard gate、authorization |
| Claude Skill adapters（同7名） | Claude Code / repository / task trigger時 / canonical link・frontmatterをstatic検査 | 7 / 62 / 4,050B | routing |
| Claude rules 4: agent-harness、backend、frontend、operations | Claude Code / repository / path発動時 / frontmatterをstatic検査 | 4 / 44 / 1,758B | routing |
| Cursor rules 4: agent-harness、backend、frontend、operations | Cursor / repository / path発動時 / frontmatterをstatic検査 | 4 / 28 / 1,812B | routing |
| `docs/agent-harness.md`、`docs/agent-principles.md`、maintenance policy | agent・reviewer・保守者 / repository / governance変更・判断 / link・budget等のみstatic検査 | 3 / 153 / 14,034B | task-state/evidence procedure、heuristic、保守基準 |
| Skill references、pilot、synthetic benchmark config | 親Skillのlazy reader / repository / 必要時のみ / link closureのみ | 8 / 371 / 19,519B | historical explanation・tool adapter。親Skillがrouteする時はactiveになり得るが、単独の正本契約ではない |
| repository外のCodex user rule / Hook config | Codex host / user / 全task・lifecycle event / runtime設定 | user rule: 1 / 93 / 12,505B; Hook: 1 / 72 / 1,844B（repo total外） | user policy・runtime/advisory（内容・command・local pathは非掲載） |

Claude/Cursorのuser-level sourceは未確認です。repository static PASSは3製品の実runtime reader発見、Hook出力、権限、sandboxを保証しません。

## Rule classification と責務

rootはhard gate、authorization、routing、minimal executionだけを保持し、principlesは設計heuristicだけを保持します。harnessはsource/readers、委任、evidence、task-state route、runtime対static/advisory境界を保持します。maintenance policyはrule/validator/fixture/self-test/workflowの追加・変更・削除基準を保持します。

maintenanceの基準は、scope、trigger、owner、enforcement、coverage、incident/risk、instruction・runner・wall-clock cost、artifact、failure owner、sunset/demotionを記録し、既存gateへ統合できない理由、replacement-before-growthを示します。workflow/jobはPR / main / scheduled / manualのtrigger locusとfailure modeを明記します。soft heuristicは自然言語exact-matchや大規模scenario fixtureで固定しません。security、authorization、data integrity、公開API、production safetyは利用可能なruntime/config/testの機械的enforcementへ結び、repositoryで強制できない部分はadvisory / unverifiedとして残します。app-only挙動は疑似実装しません。

## Metrics

表記は `lines / bytes / estimated tokens`（tokenはestimate）です。

- root: `96 / 8,934 / 1,204` → `58 / 4,853 / 771`。
- 4 canonical sources: `306 / 25,505` → `211 / 18,887`。
- effective route（root + activated Skills 4本）: `373 / 31,884 / 4,436` → `335 / 27,803 / 4,003`。
- repository instruction sources 30本: `1,073 / 80,703 / 11,201` → `978 / 74,085 / 10,581`。

workflowは4本→4本、declared jobsは20→20、matrixは21。canonical validatorは1本を維持しました。governance core（validator＋contract files）は `4 files / 453 lines / 16,179B` → `5 / 633 / 23,505B`、governance jobのfocused testは0 files→4 filesです。新しいworkflow、job、大規模fixtureは追加していません。

同一環境のlocal wall測定は、base validatorが `0.12s (user 0.06s, sys 0.02s)`、変更後validator＋4 testsが `1.03s (user 0.40s, sys 0.22s)` でした。変更後CI runnerはpendingで、PR #642の過去runner証跡は同一条件のafter測定ではありません。

## Task-state と配送状態

HEAD不一致のnegative smokeはevidenceを正しくinvalid化しました。matching HEAD/input closureのpositive inline stateではpass evidenceを再利用し、artifactや長文出力を再取得せず、残作業を選択しました。

#628/#641はmerge・close済み、#634はP2のexact-text follow-up、#644はpre-existingなimmutable Action pinningの追跡です。

## Security、publication、unknowns

公開テキストのsecurity検査対象として本報告を含め、secret、PII、raw log、session ID、local path、攻撃再現情報を掲載していません。未確認・未実行は、3製品の実runtime reader、Hook output、observed token usage、production状態、変更後CI runnerです。これらをstatic検査の成功として扱わず、CI pendingと残るruntime不確実性を完了判断へ引き継ぎます。
