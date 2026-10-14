# エージェントハーネス構成と静的検査

この文書は、WordPack固有の規則、adapter、検証入口の配置を案内します。共通作業方針は利用環境のローカル規則とユーザー依頼に従います。Codex以外の環境で作業する場合も、その環境で同等のローカル規則を利用できるようにしてください。

## 正本と参照先

| 正本 | WordPack内の役割 |
|---|---|
| `AGENTS.md`、最寄りの`AGENTS.md` | 製品固有の安全・品質条件、path別の追加条件、関連参照 |
| `.claude/rules/`、`.claude/skills/`、`.cursor/rules/` | Claude Code / Cursorからrepository内の正本へ接続するadapter |
| `.agents/skills/<name>/SKILL.md` | UI/UX、security、production調査など、対象作業に固有の参照・確認基準 |
| `docs/ai-governance/` | UI/UX品質、evidenceの採否、Issue本文の品質 |
| `docs/agent-principles.md` | WordPackの設計・実装判断heuristic |
| `docs/ai-governance/13-maintenance-policy.md` | governance文書、adapter、static validatorの保守範囲 |
| `docs/testing/index.md` | changed pathに基づくrepository CI gateと実行入口 |
| `.agents/skills/github-delivery/SKILL.md` | WordPack固有のCI gate選択、Issue / PR公開文書の参照 |
| `scripts/validate_governance.py` | governance構成と任意task-state記録のstatic検査 |

Codex、Claude Code、Cursorの各利用環境には、それぞれ適用されるローカル指示を設定してください。repository内のadapterはその環境の共通規則を置き換えず、WordPack固有の正本への案内に使います。

## Static検査の範囲

`scripts/validate_governance.py`は、定められたファイルの存在、Skill frontmatter、参照リンク、source-size、`task-state/v1`の形を検査します。`task-state.json`はvalidatorとの互換を保つ任意の構造化記録形式です。特定の作業でこの形式を作ることはrepositoryの必須条件ではありません。

Static PASSは、利用環境がローカル規則を読み込んだこと、Claude Code / Cursorの実runtime挙動、Hookや権限の適用、production状態を証明しません。これらの動作を主張する際は、対応するruntime証跡を別に確認してください。
