# Firestore 運用

この文書は Firestore インデックス、エミュレータ、シード、ローカル/CI/本番の接続先、削除運用をまとめます。環境変数の詳細は [docs/環境変数の意味.md](./環境変数の意味.md)、インフラ構成は [docs/infrastructure.md](./infrastructure.md) を参照してください。

## 基本方針

- WordPack for English は全環境で Firestore を永続層として使います。
- `FIRESTORE_EMULATOR_HOST` が設定されている場合だけ Firestore エミュレータへ接続します。
- `FIRESTORE_EMULATOR_HOST` が未設定の場合は、環境に関わらず Cloud Firestore へ接続します。
- `ENVIRONMENT` は認証やセキュリティ既定値に使い、DB 種別の切替には使いません。

## 接続先

| 環境 | 接続先 | 主な設定 |
|---|---|---|
| ローカル直起動 | Firestore Emulator | `FIRESTORE_PROJECT_ID=wordpack-local`, `FIRESTORE_EMULATOR_HOST=127.0.0.1:8080` |
| Docker Compose | Firestore Emulator | `FIRESTORE_EMULATOR_HOST=firestore-emulator:8080` |
| CI | Firestore Emulator | `ENABLE_FIRESTORE_EMULATOR=true`, `FIRESTORE_EMULATOR_PORT`, `FIRESTORE_EMULATOR_HOST=127.0.0.1:<port>` |
| 本番 | Cloud Firestore | `FIRESTORE_PROJECT_ID=<project-id>`, `FIRESTORE_EMULATOR_HOST` は未設定 |

Cloud Firestore を使う場合は、プロジェクト ID と認証情報を明示してください。本番で `FIRESTORE_EMULATOR_HOST` を設定すると本番データを読めないため、deploy 前に必ず確認します。

## インデックス

複合インデックスと single-field override は `firestore.indexes.json` で管理します。Web Console で手作業登録するのではなく、ファイルを同期します。

主な対象:

- `word_packs`: 作成日時、更新日時、lemma 重複チェック、guest 公開フィルタ
- `examples`: `word_pack_id` / `category` / `position` / `example_id`
- `articles`: Reader 記事本文、関連 WordPack link、`guest_public`
- `article_import_jobs`: 所有者、進行状態、完了した `article_id`、エラー要約
- `quizzes`: Quiz 本文、設問、Attempt link、`guest_public`
- 横断例文一覧: `created_at` / `pack_updated_at` / `lemma` / `category`
- 検索: `search_en` / `search_en_reversed` / `search_terms`

同期コマンド:

```bash
make deploy-firestore-indexes PROJECT_ID=<project-id>
```

既定では `gcloud auth print-access-token` で取得した短命の認証情報を使い、Firestore Admin API に直接 `indexes` と `fieldOverrides` を同期します。この経路は Firebase CLI 認証や `gcloud alpha` component を必要としません。

Firebase CLI を使う場合:

```bash
make deploy-firestore-indexes PROJECT_ID=<firebase-project-id> TOOL=firebase
```

`make release-cloud-run` はデプロイ前にインデックス同期を呼びます。すでに同期済みの CI/CD 環境では `SKIP_FIRESTORE_INDEX_SYNC=true` を指定できます。

## エミュレータ

ローカルで Firestore を再現する場合:

```bash
make firestore-emulator
```

または Docker Compose:

```bash
docker compose up firestore-emulator
```

エミュレータ起動時は `firestore.indexes.json` が読み込まれます。Java 21+ が必要です。環境に Java がない場合は `scripts/start_firestore_emulator.sh` が Temurin 21 の導入を試みますが、ネットワークが遮断される環境では事前に Java 21 を入れてください。

バックエンド直起動:

```bash
FIRESTORE_PROJECT_ID=wordpack-local \
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
python -m uvicorn backend.main:app --reload --app-dir apps/backend
```

Docker Compose の backend から接続する場合は `127.0.0.1` ではなく `firestore-emulator:8080` を使います。

## シード

開発用データは Firestore へ投入します。

```bash
make seed-firestore-demo
```

`.data_demo/wordpack.sqlite3.demo` は Firestore シードの元データとしてのみ使います。SQLite へ直接シードする運用はしません。

シード時の挙動:

- 例文 ID を再採番して Firestore スキーマへ正規化します。
- `examples`、`articles`、`article_word_packs` を作成します。
- ゲスト用データには `word_packs.metadata.guest_demo=true` を付与します。
- 既にゲスト用データがある場合は投入をスキップします。

再投入したい場合:

```bash
scripts/seed_firestore_demo.py --force
```

## 削除運用

`examples` の大量削除は、`word_pack_id` で絞り込んだクエリに `limit` を付け、ページングしながら `WriteBatch` で削除します。1 回あたり 500 件以内に抑えることで孤児ドキュメントと write 制限超過を避けます。

Cloud Console で手動クリーンアップする場合も、同じ条件のクエリか Firebase CLI の recursive delete を使います。

```bash
firebase firestore:delete --recursive <collection-or-document-path> --project <firebase-project-id>
```

削除前に確認すること:

- 対象 collection / document path
- 本番 project か emulator か
- guest demo data かユーザーデータか
- 関連する `examples` / `articles` / join document が残らないか

## トラブルシュート

- 一覧や検索で index error が出る: `firestore.indexes.json` を同期してください。
- ローカルで接続できない: `FIRESTORE_EMULATOR_HOST` の host と port を確認してください。
- Docker Compose で接続できない: backend コンテナからは `firestore-emulator:8080` を指定します。
- 本番でデータが見えない: `FIRESTORE_EMULATOR_HOST` が混入していないか確認してください。
- permission denied が出る: service account と IAM を確認してください。
