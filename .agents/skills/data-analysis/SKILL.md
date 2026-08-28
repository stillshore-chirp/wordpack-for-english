---
name: data-analysis
description: "Use when structured data、query結果、KPI、指標変動、funnel、forecast、causal questionを分析し、data quality、再現可能な計算、根拠付きreport、公開境界を管理する。"
---

# Data Analysis

データを根拠に判断するための専門laneです。品質未確認のsourceから強い結論を出さず、source read、計算、artifact生成、外部公開を別々の権限として扱います。

## Preflight

分析前に一度だけ固定します。

1. question、decision、metric definition、対象期間、比較baseline
2. source、owner、revisionまたはsnapshot、sample / production、grain、timezone
3. 利用tool、version、connected source、read / write / publish permission
4. quality threshold、analysis mode、artifact path、公開範囲
5. credential、個人情報、機密指標、保持・削除条件

source provenance、grain、permission、metric definitionのいずれかが欠け、結果を大きく変える場合は停止またはunknownとして残します。sample dataをproductionの観測事実へ読み替えません。

OpenAI Data Analyticsを使う場合だけ [`references/data-analytics.md`](references/data-analytics.md) を読みます。

## Workflow routing

- **Data quality**: 最初にschema、grain、completeness、uniqueness、validity、freshness、join coverageを確認します。
- **Metric diagnostics**: quality gate後に、定義、分母、segment、mix、rate、期間、tracking changeを分解します。
- **Forecast**: 十分な期間、frequency、seasonality、欠損、外生変数、backtestを確認できる場合だけ行います。
- **Causal analysis**: randomization、exposure、pre-period、confounder、interference、sample sizeを確認できる場合だけ行います。記述的分解を因果効果と呼びません。
- **Report / notebook**: 計算とsourceを追跡できるartifactを残し、表示値と本文解釈を検査します。

## Data quality gate

最低限、次を確認して結果へ残します。

- expected schemaと型、row count、期間、category coverage
- intended grainとkey uniqueness、duplicate / mixed-grain risk
- null、blank、sentinel、allowed range、cross-field rule
- freshness、late arrival、backfill、schema / definition change
- join前後のrow countとcoverage
- sample、fixture、production、derived dataの境界

gateが失敗した場合は、影響を受けない範囲だけ分析し、coverageとremediationを示します。quality failureを単なる注意書きにして全体結論を続行しません。

## Analysis contract

metric formula、numerator、denominator、unit、window、segment、timezoneを明示します。ratesとcountsを分け、aggregate changeは可能ならmix effectとwithin-segment effectへ分解します。計算値はscript、SQL、notebookのいずれかで再実行可能にし、手計算だけを正本にしません。

forecastはpoint estimateだけでなくholdout、error、interval、assumptionを示します。causal estimateはdesign、identification assumption、balance、sensitivity、limitationを示します。成立しない場合はdescriptive resultへ降格します。

## Evidence and artifact

結果は次を分離します。

- observations: sourceから直接確認した値
- calculations: 式、変換、集計、比較結果
- inferences: evidenceから導いた説明とconfidence
- recommendations: 実行案と前提
- unknowns: 未取得source、未検証仮説、coverage gap

artifactにはsource pathまたはquery identifier、snapshot、code、metric definition、quality checks、出力値を残します。表・chart・report・notebookは、数値、label、unit、欠損表示、期間、segment、本文との整合を確認します。

## Publication boundary

raw production row、個人識別子、credential、connector detail、未公開指標を公開artifactへ含めません。external publish、dashboard更新、source write、scheduled refreshは、対象と権限を特定した別の明示指示がある場合だけ行います。公開前に [`../security-publication/SKILL.md`](../security-publication/SKILL.md) を適用します。

## Required output

`question and scope`、`source and snapshot`、`quality gate`、`method`、`observations`、`calculations`、`inferences`、`recommendations`、`unknowns`、`artifact`、`publication status`を分離します。導入pilotは [`references/pilot.md`](references/pilot.md) と [`references/pilot-report.md`](references/pilot-report.md) に残します。
