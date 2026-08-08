# ドキュメント構成と責務分担

この文書は、WordPack for English のドキュメントをどこに書くかを定義する正本です。README は入口に保ち、詳細仕様や運用手順は該当する文書へ分けます。

## 責務分担

| 文書 | 責務 |
|---|---|
| `README.md` | GitHub訪問者向け入口。短い概要、screenshot、最短起動、主要directory、文書案内だけを書く。 |
| `UserManual.md` | 一般ユーザー向け操作説明。画面の使い方、できること / できないこと、guest閲覧、主要な困りごとを書く。 |
| `docs/architecture.md` | backend / frontendの責務配置、互換shim、module構造を書く。 |
| `docs/infrastructure.md` | Cloud Run、Firebase Hosting、Firestore、CI/CD、network構成の全体像を書く。 |
| `docs/deployment.md` | Cloud Run / Firebase Hosting / GitHub Actionsの実deploy手順、`.env.deploy`、IAM、dry-runを書く。 |
| `docs/環境変数の意味.md` | 環境変数の意味、既定値、誤設定時の挙動を書く。 |
| `docs/authentication.md` | Google OAuth、通常session、guest session、Cookie、認証失敗時の確認を書く。 |
| `docs/firestore.md` | Firestore index、emulator、seed、接続先、削除運用を書く。 |
| `docs/testing/` | test種別ごとの実行手順、前提、成果物、基準を書く。入口は`docs/testing/index.md`。 |
| `docs/llmops/` | Prompt Identity、生成来歴、無料のoffline評価、手動Live Evaluation、privacy方針を書く。 |
| `docs/api-reference.md` | REST APIの一覧、権限、request / response例、入力制約を書く。 |
| `docs/guest_public_api.md` | guest公開flag APIの詳細を書く。 |
| `OPERATIONS.md` | 本番監視、SLO、障害切り分け、復旧手順を書く。 |
| `AGENTS.md` | Codex・Claude Code・Cursorが常時共有する短い作業契約を書く。 |
| nested `AGENTS.md` | frontend、backend、operationsなど、対象path固有の契約を書く。 |
| `docs/agent-harness.md` | 3製品へのrule接続、instruction budget、正本・adapter・Skillの配置方針を書く。 |
| `docs/agent-principles.md` | 設計・実装のheuristicとhard gateの境界を書く。 |
| `.agents/skills/` | task固有の共有workflowを正本として書く。 |
| `.claude/rules/`, `.claude/skills/` | Claude Codeへ正本を接続する薄いadapterだけを書く。 |
| `.cursor/rules/` | Cursorへ正本を接続する薄いpath adapterだけを書く。 |
| `docs/ai-governance/` | UI/UXの詳細判定、証跡、Issue品質、完了条件を書く。 |

## README に書くこと

- product名と1〜2文の概要
- 冒頭screenshot表
- 主な機能の短い一覧
- 最短quick start
- 主要directory
- 詳細documentへの案内
- licenseや補足がある場合の短い案内

READMEの粒度は、初見訪問者が3分以内に「何のproductか」「どう起動するか」「どこを読めばよいか」を判断できる範囲までに留めます。

## README に書かないこと

- Google OAuth client作成の詳細手順
- `.env` / `.env.deploy` の全key説明
- Firestore composite index、emulator、seed、削除運用の詳細
- Cloud Run / Firebase Hostingの長いdeploy手順
- GitHub Actions本番deploy用secretやIAM roleの詳細
- 認証flow、認証失敗log key、構造化logの詳細
- test commandの長い正例 / 負例
- REST APIの詳細一覧
- troubleshootingの長文
- 実装内部の責務分割の詳細
- task固有のエージェントworkflow本文

READMEには短い要約とlinkだけを置き、詳細は該当文書を正本にします。

## 更新判断フロー

1. UIの操作、画面文言、ユーザーフローが変わる場合は`UserManual.md`を更新する。
2. API契約、HTTP status、request / response、入力制約が変わる場合は`docs/api-reference.md`と関連testを確認する。
3. 認証、session、Cookie、Google OAuth、guest権限が変わる場合は`docs/authentication.md`を更新する。
4. Firestoreのindex、接続先、seed、削除運用が変わる場合は`docs/firestore.md`を更新する。
5. deploy、Cloud Run、Firebase Hosting、GitHub Actions、IAMが変わる場合は`docs/deployment.md`と`OPERATIONS.md`を確認する。
6. 環境変数の意味や既定値が変わる場合は`docs/環境変数の意味.md`を更新する。
7. test command、artifact、CI実行条件が変わる場合は`docs/testing/index.md`と該当する`docs/testing/*.md`を更新する。
8. 全作業共通のエージェント契約が変わる場合は`AGENTS.md`を更新する。
9. path固有の契約が変わる場合はnested `AGENTS.md`とClaude / Cursor adapterを更新する。
10. task固有workflowが変わる場合は`.agents/skills/`とClaude Skill adapterを更新する。
11. rule配置、instruction budget、3製品互換性が変わる場合は`docs/agent-harness.md`と検証scriptを更新する。
12. UI/UXの詳細基準、証跡、Issue品質が変わる場合は`docs/ai-governance/`を更新する。

## エージェントルールの重複管理

- `AGENTS.md`、Skill、詳細docs、tool adapterで同じ長文を正本化しない。
- rootは常時必要な共通核、nested ruleはpath固有差分、Skillはtaskの実行順序、詳細docsは判定基準を持つ。
- `.claude/`と`.cursor/`は正本への接続だけを行い、新しい品質基準を持たない。
- 機械判定できる形式・上限・参照は`verify-agent-harness.sh`へ置く。
- 配置判断の詳細は`docs/agent-harness.md`に従う。

## 一般的な重複管理

- READMEとdocsに同じ長文を書かない。
- UserManualは一般ユーザーの操作説明に寄せ、開発者向け手順は`docs/`へ置く。
- 既存文書に正本がある場合は、新規fileを増やさず既存文書を更新する。
- 複数文書で同じ情報が必要な場合は、片方を正本にし、他方は要約とlinkだけにする。
- secret、認証情報、個人情報、本番log原文、trace / request / job IDの実値は公開文書に残さない。
