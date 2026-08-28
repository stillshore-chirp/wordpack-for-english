# Data Analytics adapter

共通のquality、analysis、artifact、publication契約は親の `SKILL.md` を正本とし、この文書にはOpenAI Data Analytics固有のsurfaceだけを置きます。

## Pinned source

- source: `openai/plugins`
- commit: `6d99ee149c9fe3c7a55b96cab062cadc1ad36a9d`
- plugin manifest version: `0.2.8`
- MCP server: `dataAnalyticsWidgets`
- capability declaration: Interactive / Read / Write
- license: Proprietary。plugin sourceをrepositoryへvendorしない

versionまたはcommitを変える場合はmanifest、MCP、skill routing、artifact format、source connector、write / publish surfaceを同じ変更で再確認します。

## Initial routing

初期導入では次へ限定します。

1. `analyze-data-quality`: sourceとgrainを確認し、分析可能範囲を固定する
2. `metric-diagnostics`: KPI変動をsegment、mix、rate、期間、tracking changeへ分解する
3. `build-report`: review可能な表とreportへまとめる

forecast、causal inference、dashboard、site publishは自動で続けません。questionとdata designが要件を満たし、権限と公開先を別途確認した場合だけ使います。

## Plugin preflight

- plugin installとversion、MCP server起動、workspace policy
- connected sourceとsource owner、read scope、query / export limit
- write、dashboard更新、site publish、external networkの可否
- artifact出力先、保持、削除、共有範囲
- sample / production、個人情報、機密指標、credentialの有無

repository pilotではsource readとlocal temporary reportだけを許可し、connector write、dashboard更新、site publishを無効として扱います。

## Unavailable handling

plugin、MCP、connected source、必要permissionのいずれかが利用不能なら、plugin固有workflowを開始しません。通常のPython / SQLで同じ分析契約を検証した場合も、Data Analytics plugin実行済みとは報告しません。`unavailable`、代替lane、coverage、再開条件を分けます。
