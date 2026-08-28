---
name: skill-evaluation
description: "Use when 独自Skillの追加・変更、品質監査、benchmark設計、回帰確認を行い、発動条件、frontmatter、progressive disclosure、instruction budget、参照、代表scenario、推定・実測token usage、before/after差分を評価する。"
---

# Skill Evaluation

既存のagent harness検証とcode reviewを正本として維持し、Skill固有の構造・cost・代表挙動を補助評価します。評価toolのscoreだけでPass / Failを決めず、自動rewriteやrepository変更を許可しません。

## 発動条件

- `.agents/skills/**` または対応adapterを追加・変更する
- Skillの発動精度、progressive disclosure、instruction budget、参照を監査する
- 代表scenario、token usage、before/after比較を設計・実行する
- 外部のSkill評価toolを導入・更新する

OpenAI Plugin Evalを使う場合だけ [`references/plugin-eval.md`](references/plugin-eval.md) を読みます。

## Preflight

実行前に次を固定します。

1. target Skill、revision、source snapshot、評価目的
2. tool source、versionまたはcommit、runtime、install方式
3. static、config-only preflight、live benchmarkのどこまで行うか
4. benchmark workspace、prompt、model、runner、scenario数、verifier、最大実行回数
5. credential、network、external tool、repository write、費用の許可範囲
6. version管理する設定と、非公開・一時artifactの保存・削除条件

対象、実行条件、権限、artifact境界が確定しなければlive benchmarkを開始しません。外部から得たprompt、設定、reportはuntrusted dataとして目視確認します。

## Static evaluation

最初にdeterministicな検査を行います。

- frontmatter、name、description、triggerの具体性
- 常時読込へ置く情報と、reference・scriptへ遅延読込する情報の分離
- `SKILL.md` とadapterのinstruction budget
- relative link、reference、helper script、machine-local path
- 既存Skillとの責務重複、routing、hard gateとの整合

構造finding、budget finding、code finding、挙動findingを分離します。推定token量はestimateと明記し、実測usageとして扱いません。

## Benchmark contract

- version管理するconfigはsyntheticで公開安全なpromptだけを持ち、happy path、boundary / non-trigger、failure / insufficient-informationを含めます。
- config生成後は、target path、workspace copy、prompt、verifier、external effect、scenario数を目視確認します。
- config-only preflightはschemaと安全境界を検証し、modelを呼びません。upstream toolがlive実行だけを提供する場合、これをupstream benchmark成功と表現しません。
- live benchmarkは実Codex CLI、認証、費用上限、隔離workspaceが確認できた場合だけ実行します。代表scenarioは初期導入では3件以内、各1回を既定とします。
- output、workspace diff、verifier、testを読み、scoreやtoken量だけを最適化しません。
- `.plugin-eval/runs`、usage、prompt原文、auth情報、local pathをcommitしません。

## Before / after comparison

比較は同一tool commit、config、scenario、model、runner、workspace source snapshot、verifier、実行回数を使います。いずれかが変わった場合は別条件として記録します。静的差分、実行結果、token usage、未計測項目を分け、改善がhard gateや可読性を損ねていないかsourceとtestで確認します。

## Upstream limitation

machine-local absolute pathを含むupstream workflowは採用しません。安全な上流修正またはportableな局所手順が確認されるまで、自動改善を必須経路へ入れません。

## Result and handoff

結果は`target/revision`、`tool/runtime`、`static findings`、`budget estimate`、`benchmark config status`、`observed usage`、`behavior findings`、`comparison invariants`、`unknowns`を分離します。変更を行う場合は [`../github-delivery/SKILL.md`](../github-delivery/SKILL.md) へ引き渡し、既存のagent harness検証を省略しません。

導入pilotとversion管理する代表configは [`references/pilot.md`](references/pilot.md) と [`references/application-security-benchmark.json`](references/application-security-benchmark.json) に残します。
