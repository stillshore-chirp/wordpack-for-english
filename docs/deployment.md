# デプロイ手順

この文書は Cloud Run、Firebase Hosting、GitHub Actions 本番デプロイ、`.env.deploy`、IAM、dry-run の手順をまとめます。監視と復旧は [OPERATIONS.md](../OPERATIONS.md) を正本にします。

## 全体像

- backend は `Dockerfile.backend` でビルドし、Cloud Run にデプロイします。
- frontend は React + Vite の build artifact を Firebase Hosting API で配置します。
- Firestore の複合インデックスと single-field override は `firestore.indexes.json` を同期します。既定の `gcloud` 経路は gcloud の認証情報で Firestore Admin API を直接呼び、Firebase CLI と `gcloud alpha` component には依存しません。
- GitHub Actions の本番デプロイは `main` への push と `workflow_dispatch` をトリガーにします。
- PR では本番デプロイ job を作らず、production deploy preflight で Cloud Run dry-run、Firebase Hosting API plan、認証済み read-only probe を非破壊で確認します。

## 事前準備

必要な CLI:

- `gcloud`
- `firebase-tools`
- Docker
- Node.js 20.19.0+
- Python 3.14

初回は次を済ませます。

```bash
gcloud auth login
gcloud auth configure-docker
firebase login
```

## `.env.deploy`

本番向け設定は `.env.deploy` にまとめます。テンプレートから複製し、実値は環境に合わせて置き換えます。

```bash
cp env.deploy.example .env.deploy
```

最低限確認する項目:

- `ENVIRONMENT=production`
- `PROJECT_ID`
- `FIRESTORE_PROJECT_ID`
- `REGION`
- `CLOUD_RUN_SERVICE`
- `ARTIFACT_REPOSITORY`
- `SESSION_SECRET_KEY`
- `ADMIN_EMAIL_ALLOWLIST`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_PROTECTION_ENABLED=true`
- `TRUSTED_PROXY_IPS`
- `ALLOWED_HOSTS`
- `GOOGLE_CLIENT_ID`
- `OPENAI_API_KEY`

`.env.deploy` は secrets を含むため、リポジトリへコミットしません。`SESSION_SECRET_KEY` は十分に長い乱数を使い、既知のサンプル値や短い値を使わないでください。

## Cloud Run dry-run

本番デプロイ前に、設定検証だけを実行できます。

```bash
./scripts/deploy_cloud_run.sh \
  --dry-run \
  --env-file .env.deploy \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend
```

この段階で Pydantic 設定、必須環境変数、Cloud Run 向け env 変換を確認します。`ENVIRONMENT=production` で `ADMIN_EMAIL_ALLOWLIST`、`TRUSTED_PROXY_IPS`、`ALLOWED_HOSTS` などが不足している場合、または `DISABLE_SESSION_AUTH=true` / `CSRF_PROTECTION_ENABLED=false` が指定されている場合は、gcloud 実行前に失敗します。

## Cloud Run デプロイ

直接スクリプトを使う場合:

```bash
./scripts/deploy_cloud_run.sh \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend \
  --artifact-repo wordpack/backend \
  --generate-secret
```

Makefile から実行する場合:

```bash
make deploy-cloud-run PROJECT_ID=<project-id> REGION=asia-northeast1
```

`--generate-secret` は `SESSION_SECRET_KEY` が未設定のときだけ乱数値を補完します。既存値を維持したい場合は `.env.deploy` にあらかじめ設定しておきます。

## release-cloud-run

本番リリースでは `make release-cloud-run` を使うと、Firestore インデックス同期、Cloud Run dry-run、本番デプロイの順序を固定できます。

```bash
DEPLOYMENT_VERSION="$(openssl rand -hex 16)"
export DEPLOYMENT_VERSION

make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy
```

Cloud Run のリクエストタイムアウトを明示する場合:

```bash
make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy \
  RUN_TIMEOUT=360s
```

紹介用の本番 URL で cold start による初回待ち時間を避けたい場合は、Cloud Run の minimum instances を `1` にします。後で費用優先へ戻す場合は `0` を指定します。

```bash
make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy \
  MIN_INSTANCES=1
```

`MIN_INSTANCES=0` は Cloud Run service の minimum instances を 0 に戻します。`MIN_INSTANCES=default` を指定すると gcloud の `--min default` に渡し、Cloud Run 側の既定値へ戻します。

既に Firestore インデックスを同期済みの CI/CD 環境では、次のように同期を省略できます。

```bash
SKIP_FIRESTORE_INDEX_SYNC=true make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=configs/cloud-run/ci.env
```

### Cloud Run の段階リリース

GitHub Actions の本番デプロイは、Cloud Run の新 revision をすぐに全面公開しません。`candidate` tag を付けて traffic 0% でデプロイし、Cloud Run が候補を ready と判定してから 10% canary を開始します。canary 中は、実際の本番経路である Firebase Hosting の `/api/config` rewrite を 60 秒間繰り返し確認します。候補 revision に設定した `DEPLOYMENT_VERSION` が応答で観測でき、全 probe request が成功した場合だけ 100% へ昇格し、その後に Firebase Hosting artifact を更新します。

canary 中の health check または traffic 更新に失敗した場合、`scripts/promote_cloud_run_revision.sh` はデプロイ前に記録した revision ごとの traffic 配分へ自動で戻します。traffic を割り当てる前の候補確認で失敗した場合は、本番 traffic に変更はありません。自動復旧自体が失敗した場合は、[OPERATIONS.md](../OPERATIONS.md) の手動 rollback を実施してください。

同じ手順を手動で実行する場合:

```bash
make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  SERVICE=wordpack-backend \
  ENV_FILE=.env.deploy \
  NO_TRAFFIC=true \
  TRAFFIC_TAG=candidate

scripts/promote_cloud_run_revision.sh \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend \
  --tag candidate \
  --canary-percent 10 \
  --attempts 7 \
  --delay-seconds 10 \
  --requests-per-attempt 10 \
  --health-url https://<firebase-project-id>.web.app/api/config \
  --expected-version "${DEPLOYMENT_VERSION}"
```

`--no-traffic` は、候補を一意に識別できるよう `--traffic-tag` と組み合わせた場合だけ受け付けます。
GitHub Actions は実行ごとにランダムな `DEPLOYMENT_VERSION` を生成し、値を log で mask して候補 revision に設定します。手動実行でも、同じ commit や image tag を再デプロイしたときに旧 revision を候補と誤認しないよう、上の例のように毎回新しい値を指定してください。未指定時だけ image tag を fallback として使います。`/api/config` は既存フィールドを維持し、`DEPLOYMENT_VERSION` が設定された revision だけ `deployment_version` も返します。これにより、初回導入時の旧 revision も同じ probe に 200 を返しつつ、revision 名や非公開 URL を workflow log に出さず、本番 traffic が候補まで到達したことを確認できます。各 probe は cache 回避用の query を付けます。

## Firebase Hosting

Firebase Hosting は frontend の静的ファイルと `/api/**` rewrite を担当します。`firebase.json` では `apps/frontend/dist` を public directory とし、API は Cloud Run へ rewrite します。

```json
{
  "hosting": {
    "public": "apps/frontend/dist",
    "rewrites": [
      {
        "source": "/api{,/**}",
        "run": {
          "serviceId": "wordpack-backend",
          "region": "asia-northeast1"
        }
      },
      { "source": "/**", "destination": "/index.html" }
    ]
  }
}
```

通常は GitHub Actions の `deploy-production.yml` が Cloud Run の後に Hosting も更新します。CI では Firebase CLI 認証に依存せず、`scripts/deploy_firebase_hosting.py` が gcloud 認証の短命 token で Firebase Hosting API を呼びます。手動運用で Firebase CLI にログイン済みの場合だけ次も使えます。

```bash
firebase deploy --only hosting --project <firebase-project-id>
```

## GitHub Actions 本番デプロイ

本番自動デプロイは `.github/workflows/deploy-production.yml` が担当します。

- `main` への push で起動します。
- 手動実行用に `workflow_dispatch` もあります。
- PR では本番 deploy job を作りません。
- CI 成功を必須にする場合は、GitHub の branch protection で必要な check を指定します。
- Cloud Run は traffic 0% の候補作成、tag URL の health check、10% canary、60 秒の継続確認、100% 昇格の順に進みます。canary 失敗時は直前の traffic 配分へ自動復旧します。
- Cloud Run の minimum instances は repository variable `CLOUD_RUN_MIN_INSTANCES` で上書きできます。未設定時は紹介用 URL の初回体験を優先して `1` を使います。費用優先へ戻す場合は `0` を設定します。

必要な repository secrets:

| Secret | 用途 |
|---|---|
| `GCP_SA_PROJECT_ID` | 本番 GCP project ID |
| `GCP_SA_KEY` | デプロイ用 service account JSON |
| `CLOUD_RUN_ENV_FILE_BASE64` | `.env.deploy` を base64 化した値 |

Firestore index 同期は `gcloud` 認証の Firestore Admin API 経由で行い、Firebase Hosting 更新は `gcloud` 認証の Firebase Hosting API 経由で行います。どちらも Firebase CLI 認証や `gcloud alpha` component に依存させません。長期保存する `FIREBASE_TOKEN` secret や、`gcloud auth print-access-token` で発行した access token の `FIREBASE_TOKEN` 代入は使いません。

### Production deploy preflight

`.github/workflows/production-deploy-preflight.yml` は、PR 時点で本番デプロイの主要な前提を非破壊で確認します。

- `pull_request` では PR コードを checkout し、secrets なしで frontend build、Cloud Run dry-run、Firebase Hosting API の `--plan-only`、production deploy contract guard を実行します。
- `pull_request_target` では secrets を使うため、PR コードは checkout せず、base branch の信頼済みコードだけで read-only probe を実行します。
- read-only probe は `gcloud auth print-access-token`、Firestore Admin API の index list、Firebase Hosting API の releases list を確認します。
- `workflow_dispatch` では選択した ref に対して同じ静的 preflight と read-only probe を手動実行できます。

この preflight は Hosting version 作成、file upload、version finalize、release 作成、Firestore index 作成/更新、Cloud Run 実デプロイを実行しません。そのため write 権限、quota、release 作成時の最終検証までは完全保証できません。実デプロイを伴わない範囲で、API path、認証前提、build artifact、dry-run 可能な設定、禁止 CLI 依存を先に検知するための check です。

サービスアカウントに必要な代表ロール:

- `roles/run.admin`
- `roles/artifactregistry.writer`
- `roles/cloudbuild.builds.editor`
- `roles/datastore.indexAdmin`
- `roles/firebasehosting.admin`
- `roles/serviceusage.serviceUsageViewer`
- `roles/iam.serviceAccountUser`

Cloud Build のソースアップロードやログ閲覧には、環境によって Cloud Storage / Cloud Build viewer 系の追加権限が必要です。権限は最小権限を基本とし、広い `roles/viewer` は切り分け目的に限ります。

## 検証

デプロイ後は次を確認します。

```bash
curl -fsS https://<api-host>/healthz
curl -fsS https://<api-host>/metrics
```

あわせて次を確認します。

- Cloud Run revision が想定 commit の image を使っている
- Firebase Hosting release が更新されている
- `/api/**` rewrite が Cloud Run へ届く
- Google ログイン、ゲスト閲覧、保存済み WordPack 一覧、WordPack 詳細、生成、TTS のうち変更影響範囲が動く

障害時の rollback と監視観点は [OPERATIONS.md](../OPERATIONS.md) を参照してください。
