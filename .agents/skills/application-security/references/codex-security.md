# Codex Security adapter

共通のscope、finding、公開、引き渡し契約は親の `SKILL.md` を正本とし、この文書にはCodex Security固有の接続だけを置きます。

## Pinned source

- source: `openai/plugins`
- commit: `6d99ee149c9fe3c7a55b96cab062cadc1ad36a9d`
- plugin manifest version: `0.1.22`
- runtime: Node.js MCP server。`CODEX_HOME`を参照する

versionまたはcommitを変える場合は、manifest、capability preflight、各scan Skill、artifact contractを同じ変更で確認します。

## Preflight record

| 項目 | 固定する内容 |
|---|---|
| plan | `diff` / `standard` / `deep`、対象revision、path、除外、完了・停止条件 |
| surface | Desktop plugin、CLI / headless、Cloudのどれを使うか |
| workspace | repository root、Git状態、read可能path、artifact出力先 |
| install | plugin version、MCP server、必要script、Node.js、host固有tool |
| permissions | source read、artifact write、connected app、外部URL、credential、production access |

repository scanでは必要なsource readとlocal artifact writeだけを使います。Issue作成や外部system更新は、別の明示依頼まで無効として扱います。

## Routing

- PR、commit、branch差分、working-tree patch: `security-diff-scan`
- repositoryまたは限定pathへの一回の監査: `security-scan`
- 明示されたexhaustive / multi-pass監査: `deep-security-scan`

Diff / Standardのterminal経路では対象file inventoryとcanonical artifactを作成し、公式finalizerで完了させます。Deepは専用coordinatorが利用可能な場合だけ開始し、prompt-only代替を行いません。

## Stop conditions

次のいずれかで開始前または途中停止します。

- target、revision、scope、permission、source provenanceが確定しない
- required preflightがreadyでない
- file inventoryまたはcanonical artifactを作れない
- plugin、server、scriptが不足し、そのmodeの公式fallbackがない
- production、credential、外部URL、connected appへの未許可accessが必要
- coverage gapまたはfinding evidenceを記録できない

停止時は`unavailable`または`partial`、coverage、保存済みartifact、未確認path、再開条件を返します。findingが0件でもcoverageが不完全ならclean resultを返しません。
