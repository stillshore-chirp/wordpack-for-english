# デプロイ手順

この文書は Cloud Run、Firebase Hosting、GitHub Actions 本番デプロイ、`.env.deploy`、IAM、dry-run の手順をまとめます。監視と復旧は [OPERATIONS.md](../OPERATIONS.md) を正本にします。

## 全体像

- backend は `Dockerfile.backend` でビルドし、Cloud Run にデプロイします。
- frontend は React + Vite の build artifact を Firebase Hosting API で配置します。
- Firestore の複合インデックスと single-field override は `firestore.indexes.json` を同期します。既定の `gcloud` 経路は gcloud の認証情報で Firestore Admin API を直接呼び、Firebase CLI と `gcloud alpha` component には依存しません。
- GitHub Actions の本番デプロイは `CI` の完了を受ける `workflow_run` 経路と、対象 SHA を明示する `workflow_dispatch` 経路だけです。自動経路は `conclusion=success`、`event=push`、`head_branch=main` を満たし、対象 SHA の一致を検証します。
- GitHub Actions から Google Cloud への認証は Workload Identity Federation（WIF）を使い、長期 service account key を workflow へ渡しません。deploy と authenticated preflight は別 provider とし、job ごとの OIDC 権限だけを付与します。
- 静的なデプロイ設定検証は `CI` の Cloud Run config guard などで行い、重複する dry-run workflow は持ちません。認証済み production deploy preflight は schedule と main ref の手動実行だけで、信頼済み main code の read-only probe を行います。

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

本番リリースでは `make release-cloud-run` を使うと、Firestore インデックス同期、Cloud Run dry-run、本番デプロイの順序を固定できます。`scripts/deploy_cloud_run.sh` の `IMAGE_TAG` と `GIT_SHA` は checkout 済み HEAD の完全 SHA を正本とし、`.env.deploy` や外部環境変数による上書きを受け付けません。`--image-tag` を渡す場合も同じ SHA の確認値である必要があります。

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

- `CI` workflow の完了を受けて起動します。自動経路は completed event の `name=CI`、`conclusion=success`、`event=push`、`head_branch=main` を検証し、`workflow_run.head_sha` をそのまま対象にします。
- CI workflow identity は固定 path `.github/workflows/ci.yml` と、live repository の API で解決した immutable workflow ID `187172373` を照合します。同一runの詳細と jobs API で canonical `Quality gate`（現行表示名: `Quality gate (selected checks)`）の completed/success も確認します。workflowを再作成してIDが変わった場合は、この定数を明示的に更新してから再開します。
- 手動の break-glass 実行は trusted `main` ref からのみ起動でき、必須入力 `target_sha` と任意の boolean input `identity_exchange_only` を受け取ります。completed状態の候補runをGitHub APIで取得し、同一 SHA の `CI` 成功・push・main runを1件確定した後、自動経路と同じrun詳細／Quality gate検証を通過してから後続 job へ進みます。
- `identity_exchange_only=true` の手動実行は `verify-target` を必ず通過した後、`production` environment の `verify-deploy-identity` で deploy 用 WIF の入力検証、pinned auth/setup-gcloud、token exchange だけを確認します。checkout、build、production env materialize、deploy、API write、traffic 操作は行わず、通常の deploy job と cutover guard は実行しません。
- 通常の自動／手動 deploy は `authorize-deploy-cutover` が repository variable `PRODUCTION_DEPLOY_ENABLED` の文字列 `true` を fail-closed に確認した場合だけ進みます。通常の production 経路を許可するまで `verify-target` の CI / Quality gate 契約は変わりません。
- checkout は検証済み対象 SHA に固定し、checkout 後の `git rev-parse HEAD` との一致を assert します。
- 自動／手動の全 production release は単一の stable concurrency group に入り、`cancel-in-progress=false` でFIFO待機します。candidate tag、traffic、rollback操作を異なるSHA間で並行させません。
- PR では本番 deploy job を作りません。
- Cloud Run は traffic 0% の候補作成、tag URL の health check、10% canary、60 秒の継続確認、100% 昇格の順に進みます。canary 失敗時は直前の traffic 配分へ自動復旧します。
- Cloud Run の minimum instances は repository variable `CLOUD_RUN_MIN_INSTANCES` で上書きできます。未設定時は紹介用 URL の初回体験を優先して `1` を使います。費用優先へ戻す場合は `0` を設定します。
- Reader文章インポートなどレスポンス後も継続する非同期ジョブのため、デプロイ環境ファイルでは `CLOUD_RUN_NO_CPU_THROTTLING=true` を設定します。`false` のままでは202応答後にバックグラウンド処理が停止し得ます。

### GitHub Actions の WIF 設定

repository variables（秘密ではない値）を、deploy と preflight の両 workflow から参照できる範囲へ登録します。

| Variable | 用途 |
|---|---|
| `GCP_PROJECT_ID` | 本番 GCP project ID |
| `GCP_DEPLOY_WIF_PROVIDER` | production deploy 用の full Workload Identity Provider resource name |
| `GCP_PREFLIGHT_WIF_PROVIDER` | authenticated preflight 用の full Workload Identity Provider resource name |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | production deploy provider が impersonate する service-account email |
| `GCP_PREFLIGHT_SERVICE_ACCOUNT` | authenticated preflight provider が impersonate する read-only service-account email |
| `PRODUCTION_DEPLOY_ENABLED` | 通常の production deploy cutover guard。初期値は `false` とし、許可時だけ文字列 `true` |

repository secret は次のとおりです。

| Secret | 用途 |
|---|---|
| `CLOUD_RUN_ENV_FILE_BASE64` | `.env.deploy` を base64 化した値 |

`PRODUCTION_DEPLOY_ENABLED` は初期値 `false` にします。main へこの変更を反映した後、`identity_exchange_only=true` の手動実行と Production deploy preflight が成功し、deploy service account の IAM disposition が完了するまで `true` に変更しません。これらの外部設定と確認が揃うまでは、通常の自動／手動 production deploy は cutover guard で停止します。

`GCP_SA_KEY` と `GCP_SA_PROJECT_ID` は移行後の workflow から参照しません。旧 key は WIF 経路の検証が完了するまで無効化・削除せず、workflow に自動 fallback を追加しないでください。

外部設定は次の順に準備します。ここに書く placeholder は実値へ置き換え、実値をこのリポジトリへコミットしません。

1. `deploy_cloud_run.sh`、Firestore Admin API、Firebase Hosting API、Cloud Run promotion、Cloud Build が実際に呼ぶ API と、deploy service account の IAM 権限を inventory します。preflight は Firestore index list と Firebase Hosting release list だけを呼ぶため、その read-only service account の権限を分けて確認します。repository の role 一覧は候補であり、live IAM の証拠ではありません。
2. Google Cloud に Workload Identity Pool と deploy / preflight それぞれの OIDC provider を作成します。issuer は `https://token.actions.githubusercontent.com/` とし、共通の claim を次のように mapping します。

   ```text
   google.subject=assertion.sub,
   attribute.repository_id=assertion.repository_id,
   attribute.repository_owner_id=assertion.repository_owner_id,
   attribute.ref=assertion.ref,
   attribute.workflow=assertion.workflow,
   attribute.workflow_ref=assertion.workflow_ref
   ```

   deploy provider にだけ `attribute.environment=assertion.environment` を追加します。authenticated preflight job は GitHub environment を参照しないため、preflight provider では存在しない `environment` claim を mapping しません。

3. provider の attribute condition は repository 名だけに頼らず、numeric ID、main ref、workflow identity へ限定します。production deploy provider の例は次のとおりです。

   ```text
   assertion.repository_id == '<REPOSITORY_ID>' &&
   assertion.repository_owner_id == '<REPOSITORY_OWNER_ID>' &&
   assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main' &&
   assertion.ref == 'refs/heads/main' &&
   assertion.environment == 'production'
   ```

   authenticated preflight provider は `environment` claim を要求せず、workflow identity までを次のように限定します。

   ```text
   assertion.repository_id == '<REPOSITORY_ID>' &&
   assertion.repository_owner_id == '<REPOSITORY_OWNER_ID>' &&
   assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/production-deploy-preflight.yml@refs/heads/main' &&
   assertion.ref == 'refs/heads/main'
   ```

4. 各 provider の identity だけに、対象 service account への `roles/iam.workloadIdentityUser` を付与します。pool全体のrepository principal setではなく、deployは `environment:production`、preflightはmain refのexact subjectへ次の形でbindingし、手順3のprovider conditionと重ねます。

   ```text
   principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/repo:stillshore-chirp/wordpack-for-english:environment:production
   principal://iam.googleapis.com/projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/subject/repo:stillshore-chirp/wordpack-for-english:ref:refs/heads/main
   ```

   deploy service account の Cloud Run、Cloud Build、Artifact Registry、Firestore index、Firebase Hosting の resource role は手順 1 の inventory と実 API の権限エラーを根拠に最小限へ確定します。preflight service account には Firestore index list の `datastore.indexes.list` だけを含む project custom role と、Firebase Hosting の最小の定義済みread-only roleである `roles/firebasehosting.viewer` を付与します。`roles/datastore.viewer` は entity read も含むためpreflightには付与しません。deploy 用の write role（`roles/run.admin`、`roles/artifactregistry.writer`、`roles/cloudbuild.builds.editor`、`roles/datastore.indexAdmin`、`roles/firebasehosting.admin` など）も付与しません。role の適用範囲と実効権限は live IAM inventory で確認します。
5. provider resource name、対象 service account email、project ID を上記 variables へ登録し、両 workflow の安全な token exchange と preflight read-only probe を確認します。provider、variables、IAM binding、exchange が準備できるまで、この repository 変更を merge-ready と判断しません。

deploy と preflight は専用 provider と専用 service account を使います。preflight service account は Firestore index list と Firebase Hosting release list の read-only probe に必要な権限だけを持たせ、Cloud Run deploy、Cloud Build、Artifact Registry upload、Firestore index update、Hosting release write の権限を付与しません。

Firestore index 同期は `gcloud` 認証の Firestore Admin API 経由で行い、Firebase Hosting 更新は `gcloud` 認証の Firebase Hosting API 経由で行います。どちらも Firebase CLI 認証や `gcloud alpha` component に依存させません。長期保存する `FIREBASE_TOKEN` secret や、`gcloud auth print-access-token` で発行した access token の `FIREBASE_TOKEN` 代入は使いません。

### Production deploy preflight

`.github/workflows/production-deploy-preflight.yml` は、信頼済み main code に対する認証済みの read-only probe を定期または main ref の手動実行で確認します。静的な preflight は `CI` lane が担当します。

- trigger は schedule と `workflow_dispatch` です。手動実行では `refs/heads/main` の場合だけ authenticated job が実行され、常に `main` を checkout します。
- read-only probe は `gcloud auth print-access-token`、Firestore Admin API の index list、Firebase Hosting API の releases list を確認します。
- `GCP_PROJECT_ID`、provider、service-account variable が欠けているか形式不正の場合は skip せず fail-closed で停止します。

この preflight は Hosting version 作成、file upload、version finalize、release 作成、Firestore index 作成/更新、Cloud Run 実デプロイを実行しません。そのため write 権限、quota、release 作成時の最終検証までは完全保証できません。API path と認証前提の read-only 到達性を確認するもので、frontend build、Cloud Run dry-run、deploy contract の静的検証は `CI` lane で行います。

production deploy service account に必要な代表ロール:

- `roles/run.admin`
- `roles/artifactregistry.writer`
- `roles/cloudbuild.builds.editor`
- `roles/datastore.indexAdmin`
- `roles/firebasehosting.admin`
- `roles/serviceusage.serviceUsageViewer`
- `roles/iam.serviceAccountUser`

authenticated preflight service account は次の read-only role に限定します。

- `datastore.indexes.list` だけを含む project custom role
- `roles/firebasehosting.viewer`（Hosting resource の read-only access。release list の API 到達性を確認する）

preflight service account に `roles/datastore.viewer`やproduction deploy 用 roleを追加しないことが repository 外部設定の hardening 条件です。safe exchange / read-only probe が不足permissionで失敗した場合だけ、エラーで要求されたpermissionを個別に確認します。

Cloud Build のソースアップロードやログ閲覧には、環境によって Cloud Storage / Cloud Build viewer 系の追加権限が必要です。権限は最小権限を基本とし、広い `roles/viewer` は切り分け目的に限ります。

### WIF 移行後の rollback と旧 key の扱い

WIF の token exchange が失敗した場合、workflow は長期 key へ自動 fallback せず停止します。repository 側の緊急 rollback は workflow 変更を明示的に revert する手順で行い、旧 key の再有効化は対象 key と理由を特定した別の外部権限で実施します。

`GCP_SA_KEY` を無効化できる条件は、両 workflow が key-free であること、両 provider の exchange と authenticated preflight が成功すること、deploy/preflight 各 service account の必要な IAM binding と preflight read-only role が確認済みであることです。production canary / deploy の実行や traffic 変更は別途明示許可が必要です。無効化後の観測・rollback 窓で旧 key の参照がないことを確認し、削除はその後に明示的な GCP 権限で行います。無効化・削除の実施結果は repository の秘密値や token を含めずに運用記録へ残します。

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
