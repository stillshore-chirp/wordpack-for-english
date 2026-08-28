# Static pilot: application-security Skill

## Scope

- target: `.agents/skills/application-security`
- baseline fixture: `tests/fixtures/plugin-eval/application-security-before`
- source: pinned Plugin Eval commit documented in `plugin-eval.md`
- execution: PR workflowのread-only static evaluation
- live Codex benchmark: not run

## Scenarios

1. baseline fixtureのbroken relative linkを`analyze`が検出する
2. canonical Skillでは同じfailureがなく、`compare`がresolved failureとして示す
3. canonical Skillのsupport file、budget breakdown、measurement planをJSON artifactとして確認する
4. `application-security-benchmark.json`のschema、workspace、sandbox、approval、scenario数を検証して停止する

## Evidence boundary

workflow artifactはrunner tempだけに保存し、repositoryへcommitしません。static scoreやgradeは参考値です。live benchmarkはcredential、費用、実Codex実行、workspace writeを伴うため、このpilotの対象外です。推定budgetと実測usageは混同せず、observed usageは未計測として扱います。

## Upstream compatibility note

固定したCLIはsimulated `--dry-run`を廃止しています。Issue作成時の想定を偽装せず、config reviewとschema verificationをpreflightとして採用します。自動rewrite用の`improve-skill` workflowはportableな再現性を確認できないため必須経路へ含めません。
