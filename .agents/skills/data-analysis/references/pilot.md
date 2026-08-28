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

## Deterministic lane pilot

`verify_data_analysis_pilot.py`で次を実行します。

- schema、grain、null、duplicate、range、channel coverage、freshnessを検証
- 最新2週のaggregate rateとchannel別rateを計算
- aggregate差分をchannel-mix effectとwithin-channel rate effectへ分解
- observation、calculation、inference、recommendation、unknown、publication boundaryを分けたMarkdown reportを生成
- 生成reportをreview済みの [`pilot-report.md`](pilot-report.md) とbyte単位で比較

## Result

- quality gate: synthetic pilotの宣言範囲でPASS
- deterministic analysis: PASS
- Data Analytics plugin execution: unavailable
- production coverage: none
- causal claim: none
- public artifact: synthetic aggregate report only
