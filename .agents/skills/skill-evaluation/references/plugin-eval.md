# Plugin Eval adapter

共通契約は親の `SKILL.md` を正本とし、このreferenceはPlugin Eval固有の情報だけを保持します。

## Pinned source

- source: `openai/plugins`
- commit: `6d99ee149c9fe3c7a55b96cab062cadc1ad36a9d`
- plugin manifest version: `0.1.2`
- package: private local CLI
- runtime: Node.js `>=20`

installは上記commitのlocal checkoutから行い、plugin本体、`node_modules`、credentialをこのrepositoryへvendorしません。versionを変える場合はmanifest、CLI、benchmark schema、artifact挙動を再確認します。

## Supported lanes

- static: `analyze`、`explain-budget`、`measurement-plan`
- config: `init-benchmark`でschema version 2の設定を生成
- live: `benchmark`が実際の`codex exec`を隔離workspaceで実行
- comparison: `compare`でbefore / after reportを比較

このcommitのCLI実装はsimulated dry-runを提供せず、`--dry-run`を拒否します。一方、同commitの`evaluate-skill`文書には`benchmark --dry-run`の例が残っています。repositoryでは [`validate_plugin_eval_benchmark.py`](../../../../scripts/validate_plugin_eval_benchmark.py) をconfig-only preflightとして使い、upstream benchmark実行と混同しません。

## Live preflight

live実行前に、次を目視確認します。

- `workspace.sourcePath`、copy / worktree方式、保存条件
- scenario promptと最大実行回数
- model、sandbox、approval policy、extra arguments
- verifier commandと生成物
- temp `CODEX_HOME`へcopyされるauth / configのsource
- network、external tool、費用、repository外writeの可否

Codex CLI、認証、費用上限のいずれかが確認できなければlive benchmarkは`unavailable`です。usage telemetryがなければ実測tokenは`unavailable`または`partial`とします。

## Artifact boundary

version管理するのはreview済みのsynthetic benchmark configと公開安全なsummaryだけです。`.plugin-eval/`配下のrun、usage、logs、workspace、prompt原文、絶対pathはignoreし、必要な非公開artifactは承認済みprivate storageに限定します。

## Upstream improve-skill

このcommitの`improve-skill`は特定開発者ホームを指す絶対pathを含むため非採用です。portableな上流修正を確認するまで、自動rewriteへ利用しません。
