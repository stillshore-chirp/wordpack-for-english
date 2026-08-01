# ドキュメント構成と責務分担

この文書は、WordPack for English のドキュメントをどこに書くかを定義する正本です。README は入口に保ち、詳細仕様や運用手順は該当する文書へ分けます。

## 責務分担

| 文書 | 責務 |
|---|---|
| `README.md` | GitHub 訪問者向け入口。短い概要、スクリーンショット、最短起動、主要ディレクトリ、文書案内だけを書く。 |
| `UserManual.md` | 一般ユーザー向け操作説明。画面の使い方、できること/できないこと、ゲスト閲覧、主要な困りごとを書く。 |
| `docs/architecture.md` | backend/frontend の責務配置、互換 shim、モジュール構造を書く。 |
| `docs/infrastructure.md` | Cloud Run、Firebase Hosting、Firestore、CI/CD、ネットワーク構成の全体像を書く。 |
| `docs/deployment.md` | Cloud Run / Firebase Hosting / GitHub Actions の実デプロイ手順、`.env.deploy`、IAM、dry-run を書く。 |
| `docs/環境変数の意味.md` | 環境変数の意味、既定値、誤設定時の挙動を書く。 |
| `docs/authentication.md` | Google OAuth、通常セッション、ゲストセッション、Cookie、認証失敗時の確認を書く。 |
| `docs/firestore.md` | Firestore インデックス、エミュレータ、シード、接続先、削除運用を書く。 |
| `docs/testing/` | テスト種別ごとの実行手順、前提、成果物、基準を書く。入口は `docs/testing/index.md`。 |
| `docs/llmops/` | Prompt Identity、生成来歴、無料のオフライン評価、完全手動の Live Evaluation、privacy 方針を書く。 |
| `docs/api-reference.md` | REST API の一覧、権限、request / response 例、入力制約を書く。 |
| `docs/guest_public_api.md` | ゲスト公開フラグ API の詳細を書く。 |
| `OPERATIONS.md` | 本番監視、SLO、障害切り分け、復旧手順を書く。 |
| `AGENTS.md` | AI エージェントの実行手順、完了ゲート、必須確認を書く。 |
| `.agents/skills/` | AI エージェントが使う具体的な作業ワークフローを書く。 |

## README に書くこと

- プロダクト名と 1〜2 文の概要
- 冒頭スクリーンショット表
- 主な機能の短い一覧
- 最短クイックスタート
- 主要ディレクトリ
- 詳細ドキュメントへの案内
- ライセンスや補足がある場合の短い案内

README の粒度は、初見の訪問者が 3 分以内に「何のプロダクトか」「どう起動するか」「どこを読めばよいか」を判断できる範囲までに留めます。

## README に書かないこと

- Google OAuth クライアント作成の詳細手順
- `.env` / `.env.deploy` の全キー説明
- Firestore 複合インデックス、エミュレータ、シード、削除運用の詳細
- Cloud Run / Firebase Hosting の長いデプロイ手順
- GitHub Actions 本番デプロイ用シークレットや IAM ロールの詳細
- 認証フロー、認証失敗ログキー、構造化ログの詳細
- テストコマンドの長い正例/負例
- REST API の詳細一覧
- トラブルシューティングの長文
- 実装内部の責務分割の詳細

README には短い要約とリンクだけを置き、詳細は該当文書を正本にします。

## 更新判断フロー

1. UI の操作、画面文言、ユーザーフローが変わる場合は `UserManual.md` を更新します。
2. API 契約、HTTP status、request / response、入力制約が変わる場合は `docs/api-reference.md` と関連テストを確認します。
3. 認証、セッション、Cookie、Google OAuth、ゲスト権限が変わる場合は `docs/authentication.md` を更新します。
4. Firestore のインデックス、接続先、シード、削除運用が変わる場合は `docs/firestore.md` を更新します。
5. デプロイ、Cloud Run、Firebase Hosting、GitHub Actions、IAM が変わる場合は `docs/deployment.md` と `OPERATIONS.md` を確認します。
6. 環境変数の意味や既定値が変わる場合は `docs/環境変数の意味.md` を更新します。
7. テストコマンド、成果物、CI 実行条件が変わる場合は `docs/testing/index.md` と該当する `docs/testing/*.md` を更新します。
8. AI エージェントの作業手順や完了条件が変わる場合は `AGENTS.md` を更新し、長文の詳細は専用 docs へ置きます。

## 重複管理を避ける基準

- README と docs に同じ長文を書かない。
- UserManual は一般ユーザーの操作説明に寄せ、開発者向け手順は `docs/` へ置く。
- 既存文書に正本がある場合は、新規ファイルを増やさず既存文書を更新する。
- 複数文書で同じ情報が必要な場合は、片方を正本にし、他方は要約とリンクだけにする。
- secret、認証情報、個人情報、本番ログ原文、trace / request / job ID の実値は公開文書に残さない。
