# Sample metric-diagnostics pilot

## Contract

- date: 2026-08-28
- source: `tests/fixtures/data-analysis/weekly-metrics.csv`
- source class: synthetic sample、公開可、個人情報なし
- question: 最新週のpaid conversion rate変化を説明する
- permitted: repository source read、temporary report write
- prohibited: production、credential、connected source、external publish、dashboard write

## Plugin preflight

現在のworkspaceではData Analytics plugin、`dataAnalyticsWidgets` MCP、connected data sourceを利用できません。plugin固有workflowは開始せず、statusは`unavailable`です。install、workspace policy、source permission、artifact destinationの確認を再開条件とします。

## Workflow selection

初期採用は、現在のrepositoryで利用頻度が高く、source要件をsynthetic CSVでも満たせ、artifactと検証costを小さく保てる3 laneに限定します。

| Workflow | 選定理由 | source要件 | artifact / 検証cost |
|---|---|---|---|
| `analyze-data-quality` | すべての分析の入口として再利用頻度が高い | schema、grain、null、duplicate、range、freshnessを読めるsource | quality gate付きreport、決定的な低cost検証 |
| `metric-diagnostics` | KPI変動の調査で再利用頻度が高い | 比較期間、分母、segment、mix、rateを含むsource | 計算scriptと表、fixtureで再計算可能 |
| `build-report` | reviewと公開境界を揃えるため必要 | quality gateを通過した集計結果 | Markdown report、構造・数値の決定的検証 |

forecast、causal inference、notebook、visualization、dashboard、site publishは初期対象から見送ります。十分な時系列・backtest、実験設計、connected source、rendered artifact、公開権限が必要で、現在のworkspaceではsourceとpluginが利用不能なため、検証costと公開リスクが高くなるためです。

## Deterministic lane pilot

`verify_data_analysis_pilot.py`で次を実行します。

- schema、grain、null、duplicate、range、channel coverage、freshnessを検証
- 最新2週のaggregate rateとchannel別rateを計算
- aggregate差分をchannel-mix effectとwithin-channel rate effectへ分解
- observation、calculation、inference、recommendation、unknown、publication boundaryを分けたMarkdown reportを生成
- 生成reportをreview済みの [`pilot-report.md`](pilot-report.md) とbyte単位で比較
- 生成reportの見出し順、空セクション、表の列数・区切り・データ行、機械ローカルpathを`validate_report_layout`で検査

## Result

- quality gate: synthetic pilotの宣言範囲でPASS
- deterministic analysis: PASS
- Data Analytics plugin execution: unavailable
- production coverage: none
- causal claim: none
- public artifact: synthetic aggregate report only
