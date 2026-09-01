# デプロイ手順

この文書は Cloud Run、Firebase Hosting、GitHub Actions 本番デプロイ、`.env.deploy`、IAM、dry-run の手順をまとめます。監視と復旧は [OPERATIONS.md](../OPERATIONS.md) を正本にします。

## 全体像

- backend は `Dockerfile.backend` から既存の production workflow の build job で一度だけビルドし、検証済みの Artifact Registry digestを Cloud Run にデプロイします。
- frontend は React + Vite の build artifact を Firebase Hosting API で配置します。
- Firestore の複合インデックスと single-field override は `firestore.indexes.json` を同期します。既定の `gcloud` 経路は gcloud の認証情報で Firestore Admin API を直接呼び、Firebase CLI と `gcloud alpha` component には依存しません。
- GitHub Actions の本番デプロイは、`CI` の `quality_gate` 後に同じrun内で呼び出す `workflow_call` 経路と、対象 SHA を明示する `workflow_dispatch` 経路だけです。自動経路は呼び出し元runの `name=CI`、`event=push`、`head_branch=main`、対象 SHA、実行中の `Quality gate (selected checks)` 成功を照合します。PR / develop push からは呼び出しません。
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
  --service wordpack-backend \
  --image-uri <region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
```

この段階で Pydantic 設定、必須環境変数、Cloud Run 向け env 変換を確認します。`ENVIRONMENT=production` で `ADMIN_EMAIL_ALLOWLIST`、`TRUSTED_PROXY_IPS`、`ALLOWED_HOSTS` などが不足している場合、または `DISABLE_SESSION_AUTH=true` / `CSRF_PROTECTION_ENABLED=false` が指定されている場合は、gcloud 実行前に失敗します。
backend imageを手動で準備するときも、作業treeを直接Cloud Buildへ渡さず、`scripts/build_backend_artifact.sh` に対象SHAと専用build service accountを渡します。このhelperは `git archive TARGET_SHA` でmode 700のprivate temporary contextを作り、明示的な `.gcloudignore` allowlistで `Dockerfile.backend`、build config、requirements、backend runtime sourceだけをCloud Buildへ一度だけsubmitします。dirty・untracked inputはarchiveへ入らず、trackedのenv・credential・generated fileもCloud Build stagingから除外されます。digest-only deploy helperのdry-runと本番実行はCloud Buildを送信せず、builder credentialも受け取りません。表示・出力するのはimage name/URI/digestと `native_provenance_snapshot_sha256` だけです。

## Cloud Run デプロイ

直接スクリプトを使う場合:

```bash
./scripts/deploy_cloud_run.sh \
  --env-file .env.deploy \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend \
  --artifact-repo wordpack/backend \
  --image-uri <region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex> \
  --generate-secret
```

Makefile から実行する場合:

```bash
make deploy-cloud-run PROJECT_ID=<project-id> REGION=asia-northeast1 IMAGE_URI=<immutable-image-uri>
```

`--generate-secret` は `SESSION_SECRET_KEY` が未設定のときだけ乱数値を補完します。既存値を維持したい場合は `.env.deploy` にあらかじめ設定しておきます。

## release-cloud-run

本番リリースでは `make release-cloud-run` を使うと、Firestore インデックス同期、Cloud Run dry-run、本番デプロイの順序を固定できます。production の deploy helper は build を実行せず、事前に検証した Artifact Registry の immutable digest（`@sha256:<64-hex>`）だけを受け取ります。`IMAGE_URI` をタグのまま渡した場合、project / repository / digest の検証で停止します。build時の `BUILD_SERVICE_ACCOUNT=<build-service-account-email>` は既存の production workflow が一度だけ使い、deploy helperへは渡しません。

```bash
DEPLOYMENT_VERSION="$(openssl rand -hex 16)"
export DEPLOYMENT_VERSION

make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy \
  IMAGE_URI=<region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
```

### backend image の build-once、digest、provenance、SBOM

既存の `Deploy to production` workflow には、artifactを明示的に受け渡す4段階（`prepare-release-artifacts`、`build-backend-artifact`、`attest-backend-artifact`、`deploy`）があります。新しいworkflowは増やしていません。各jobの責務と境界は次のとおりです。

- `prepare-release-artifacts` は検証済み `target_sha` をcheckoutしてfrontendをbuildし、`frontend-release-dist` を1日だけ保存します。GCP/OIDC権限とproduction environmentを持ちません。
- `build-backend-artifact` は `production` environment の承認後にだけ、専用build service accountでWIF認証します。`git archive TARGET_SHA` のprivate contextをCloud Buildへ一度だけsubmitし、build resultとArtifact Registry manifest digest、native provenance、同digestのhealth smokeを検証します。検証済みimmutable registry digest imageからtarget SHAに結び付くdeterministicなlocal handoff tagを作り、同じimage IDを確認したtagを圧縮archiveにして `backend-image-archive` として1日だけhandoffし、archiveのSHA-256を後続jobへ渡します。artifact upload前にGoogle credentialを削除します。
- `attest-backend-artifact` はhandoff archiveのSHA-256を検証してから別runnerでloadし、復元されたtarget SHAのlocal handoff tagを確認します。依存を隔離した状態で、checksum-pinned Syft 1.51.1 CLIをlocal Docker daemonのhandoff tagへ実行します。SPDX 2.3を厳密検証し、GitHub APIのrepository-scoped storageへ `actions/attest` で同じregistry image name/digestをsubjectとするdelivery provenanceとSBOMを保存し、検証用metadataを1日だけhandoffします。Anchore Actionは使用しません。Google credentialはこのjobへ渡しません。
- `deploy` は2回目の `production` environment 承認後、frontendとattestation metadataをdownloadします。GCPへWIFで再認証し、private GAR向けDocker authを設定した後、`gh attestation verify` を同じexact digestに対して実行します。検証成功後にだけproduction envをmaterializeし、既存のCloud Run candidate/canary/health/rollbackとFirebase Hostingの順序へ進みます。

通常のartifact経路では `build-backend-artifact` と `deploy` の両方に `environment: production` が設定されるため、各jobでenvironment承認が発生し得ます。manual `identity_exchange_only` 経路も同environmentでWIF交換だけを確認します。jobを分ける理由は、job-wide OIDC/permissionsを最小化し、build用Cloud Build・Syft・attestation・deploy用SDK/secretの依存ツールを隔離し、credential cleanupとartifact handoffを機械的にするためです。既存workflow内のjob追加で足りるため、新workflowや通常PRのpublish経路は増やしません。

- 対象 source は `verify-target` が確認した `target_sha`（40文字の完全SHA）です。
- Cloud Build は `cloudbuild.backend.yaml` でタグ付きの一時参照を push し、workflow が build result と Artifact Registry の manifest digest を照合します。health smoke、actions/attestのsubject、Cloud Run deployは同じ完全なregistry `IMAGE_URI`（`@sha256:<64-hex>`）に結び付きます。build jobはその検証済みimageからtarget SHAのlocal handoff tagを作り、同じimage IDを確認してarchiveとSHA-256をattest jobへ渡します。SBOMの生成入力とload後の確認にはregistry digestではなく、このlocal handoff tagを使います。
- GitHub Actions の artifact attestation は GitHub API の repository-scoped storage に subject digest として保存します。GitHub workflowのdelivery証跡には project-owned custom predicate type `https://github.com/stillshore-chirp/wordpack-for-english/attestations/backend-delivery/v1` を使い、payload内の `runDetails.builder.id` は exact `BUILDER_WORKFLOW` URI、`buildDefinition.buildType` は `${BUILDER_WORKFLOW}#backend-cloud-build-v1` とします。`underlyingBuilder=https://cloudbuild.googleapis.com/GoogleHostedWorker` と `cloudBuildProvenance=required` は、上流のCloud Build native provenanceとの対応を示すdelivery predicate値として検証します。これはGitHub署名証明書がGoogle builder identityを示すという意味ではありません。Cloud Build 自体の native provenance は reserved SLSA predicate `https://slsa.dev/provenance/v1` として `gcloud artifacts docker images describe <image>@<digest> --show-provenance --format=json` で同じ完全digestについて取得し、image digest、GoogleHostedWorker、build invocation、`_SOURCE_REPOSITORY` / `_TARGET_SHA` / `_BUILDER_WORKFLOW` substitutionを検証します。local archive submitではSCM metadataが省略され得ますが、存在する場合はrepository、`refs/heads/main`、target SHAを厳密照合します。検証済みJSONのSHA256を `nativeProvenanceSnapshotSha256` としてcustom delivery predicateへ結合し、Cloud Build側では `options.requestedVerifyOption: VERIFIED` を独立して要求します。expected repository、signer workflow、source ref、source digest、signer digest、target SHA、builder、digest が一つでも欠ける・不一致の場合は Cloud Run に進みません。
- SBOM はchecksum-pinned Syft 1.51.1 CLIで生成した SPDX JSON（attestation predicate type: `https://spdx.dev/Document/v2.3`）をdigestに結び付け、attestation と同じ対象を示します。Anchore Actionは使用しません。raw secret、token、`.env.deploy` の内容は SBOM、attestation、summary、log に含めません。
- `scripts/deploy_cloud_run.sh` は immutable digest の deploy 専用です。build、tag解決、別project / repositoryへの読み替えを行わず、候補の traffic 0%、canary、health、rollback の既存順序を維持します。

手動で build と検証対象を準備する場合の例です。対象SHAをcheckout済みのtreeから実行し、値は実環境の識別子へ置き換え、production deploy の明示許可と `main` の completed CI / Quality gate success を別途確認します。CI run 全体の conclusion は、automatic deploy failure 後の manual retry では条件にしません。

```bash
export TARGET_SHA="<40-char-main-commit-sha>"
export REPOSITORY="<owner>/<repository>"
export BUILDER_WORKFLOW="https://github.com/${REPOSITORY}/.github/workflows/deploy-production.yml@refs/heads/main"
export GITHUB_OUTPUT="$(mktemp)"
trap 'rm -f "${GITHUB_OUTPUT}"' EXIT

scripts/build_backend_artifact.sh \
  --project-id "<project-id>" \
  --region "<region>" \
  --artifact-repo wordpack/backend \
  --repository "${REPOSITORY}" \
  --target-sha "${TARGET_SHA}" \
  --builder-workflow "${BUILDER_WORKFLOW}" \
  --build-service-account "<build-service-account>@<project-id>.iam.gserviceaccount.com"

export IMMUTABLE_IMAGE="$(sed -n 's/^image_uri=//p' "${GITHUB_OUTPUT}")"
export IMAGE_DIGEST="$(sed -n 's/^image_digest=//p' "${GITHUB_OUTPUT}")"
export NATIVE_PROVENANCE_SNAPSHOT_SHA256="$(sed -n 's/^native_provenance_snapshot_sha256=//p' "${GITHUB_OUTPUT}")"
[[ "${IMMUTABLE_IMAGE}" =~ @sha256:[0-9a-f]{64}$ ]]
[[ "${NATIVE_PROVENANCE_SNAPSHOT_SHA256}" =~ ^sha256:[0-9a-f]{64}$ ]]
export SOURCE_DIGEST="<40-char-github.sha>"
export SIGNER_DIGEST="<40-char-github.workflow_sha>"
```

GitHub API 上の attestation を確認する例:

```bash
gh attestation verify "oci://${IMMUTABLE_IMAGE}" \
  --repo "<owner>/<repository>" \
  --signer-workflow "<owner>/<repository>/.github/workflows/<trusted-workflow>.yml" \
  --source-ref refs/heads/main \
  --source-digest "${SOURCE_DIGEST}" \
  --signer-digest "${SIGNER_DIGEST}"

gh attestation verify "oci://${IMMUTABLE_IMAGE}" \
  --repo "<owner>/<repository>" \
  --signer-workflow "<owner>/<repository>/.github/workflows/<trusted-workflow>.yml" \
  --source-ref refs/heads/main \
  --source-digest "${SOURCE_DIGEST}" \
  --signer-digest "${SIGNER_DIGEST}" \
  --predicate-type https://spdx.dev/Document/v2.3
```

`--source-digest` はattestation certificateに記録されたsource repository digest（workflowでは `github.sha`）です。`--signer-digest` は署名に使ったworkflow file revision（workflowでは `github.workflow_sha`）です。build対象の `TARGET_SHA` はCloud Buildへ渡すcommitであり、custom delivery predicateの `targetSha` と `resolvedDependencies[].digest.gitCommit` へ別に固定します。helperの `GITHUB_OUTPUT` は `image_name`、`image_digest`、`image_uri`、`native_provenance_snapshot_sha256` だけを含み、Cloud Build build IDは内部照合に限定して公開しません。

helperが `--show-provenance` で取得したnative provenance JSONは、同じimage digest、GoogleHostedWorker、invocation、custom substitutionsを検証してからSHA256化し、`nativeProvenanceSnapshotSha256` としてproject-owned custom delivery predicateに結び付けます。local archive submitのためSCM metadataが空でも受け入れますが、返された場合はrepository/ref/SHAを照合します。build jobは検証済みregistry digest imageをtarget SHAのlocal handoff tagへ付け替え、同じimage IDを確認してarchive SHA-256とともにhandoffします。SBOMはattest jobがarchive checksumを確認してtagを復元した後、checksum-pinned Syft 1.51.1をlocal Docker daemonのhandoff tagへ実行して生成します。actions/attestのsubjectとCloud Run deployは引き続きregistryのimmutable digestを使います。

Cloud Build v1 native provenanceでは、SCM由来の `buildConfigSource` と手動submit由来のbase64 inline `buildConfig` のどちらか一方を必須にします。local archive submitでSCM metadataが省略された場合も、空でないinline `buildConfig` がなければ証跡形状の不一致として停止します。

native provenanceのJSONは `gcloud artifacts docker images describe <image>@<digest> --show-provenance --format=json` で取得し、検証済みsnapshotのSHA256を `native_provenance_snapshot_sha256` / `nativeProvenanceSnapshotSha256` として受け渡します。Container Analysis API（`containeranalysis.googleapis.com`）と、project-level `roles/containeranalysis.occurrences.viewer` を持つdeploy service accountが必要です。Cloud Buildのbuild IDはinvocation照合の内部値であり、workflow output、summary、attestation、logには出しません。

deploy jobはGCPへWIFで再認証してprivate GARへアクセス可能にした後、`gh attestation verify` を実行します。GitHub署名済みworkflowのdelivery provenanceと、Google Cloud Buildが発行するnative provenanceは別の証跡です。前者のsigner digestは `github.workflow_sha`、source digestは `github.sha`、後者のbuild対象は `TARGET_SHA` であり、GitHub署名者がGoogle builder identityを表すわけではありません。

digestを指定して候補をデプロイする例:

```bash
IMAGE_URI="${IMMUTABLE_IMAGE}" \
make release-cloud-run \
  PROJECT_ID="<project-id>" \
  REGION="<region>" \
  SERVICE=wordpack-backend \
  ENV_FILE=.env.deploy \
  NO_TRAFFIC=true \
  TRAFFIC_TAG=candidate
```

上記の `[[ ... ]]` は説明用の検査形だけを示したもので、実際には `IMAGE_DIGEST` を registry manifest の完全値として比較します。local command は GitHub attestation storage、GitHub signer policy、Cloud Build native provenance / builder identity、Artifact Registry retention、Cloud Run IAM の live 設定を証明しません。production workflow の verify step と外部設定の inventory を正本とします。

prepare/build/attest/deploy のrunner分離、image archiveの転送、Cloud Build実行、SBOM生成、attestation検証によりrunner wall time、Cloud Build時間、Artifact Registry / GitHub保存量が増えます。frontend、backend image、attestation metadataのhandoff artifactはworkflowで各1日だけ保持し、runnerのworkspace、private archive、一時env、SBOM、credentialは各jobのcleanupで削除します。release operatorが全段階の一次failure ownerであり、Cloud Build/IAM不一致はbuild担当、SPDX/attestation不一致はsecurity/release担当、Cloud Run/Hosting/canary/rollback不一致はdeploy担当が切り分けます。どの段階でも最初の不一致（build result、registry digest、native provenance、health smoke、SBOM、attestation）を記録し、Cloud Run / traffic / Hosting write前に停止します。

job分離のsunsetまたはdemotionは自動で行いません。承認済みリリースの安定実績、1日artifact cleanup、runner/Cloud Build quota/GitHub・Artifact Registry storageの測定、job-wide OIDCと依存tool隔離が不要になったことをIssue/PRで証跡化し、digest、source/signer/target境界、attestation、rollback、credential cleanupを保った設計へ置換できる場合だけ変更します。Syft、native provenance、GitHub attestationの失敗が続く場合はcutoverを無効化してfail closedとし、検証を省略するdemotionは行いません。DependabotによるActions更新後は、full SHA pin、attestation scope、SBOM入力、1日retentionを `workflow_contract` で再確認します。

Cloud Run のリクエストタイムアウトを明示する場合:

```bash
make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy \
  RUN_TIMEOUT=360s \
  IMAGE_URI=<region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
```

紹介用の本番 URL で cold start による初回待ち時間を避けたい場合は、Cloud Run の minimum instances を `1` にします。後で費用優先へ戻す場合は `0` を指定します。

```bash
make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=.env.deploy \
  MIN_INSTANCES=1 \
  IMAGE_URI=<region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
```

`MIN_INSTANCES=0` は Cloud Run service の minimum instances を 0 に戻します。`MIN_INSTANCES=default` を指定すると gcloud の `--min default` に渡し、Cloud Run 側の既定値へ戻します。

既に Firestore インデックスを同期済みの CI/CD 環境では、次のように同期を省略できます。

```bash
SKIP_FIRESTORE_INDEX_SYNC=true make release-cloud-run \
  PROJECT_ID=<project-id> \
  REGION=asia-northeast1 \
  ENV_FILE=configs/cloud-run/ci.env \
  IMAGE_URI=<region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
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
  IMAGE_URI=<region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex> \
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
GitHub Actions は実行ごとにランダムな `DEPLOYMENT_VERSION` を生成し、値を log で mask して候補 revision に設定します。手動実行でも、同じ commit や digest を再デプロイしたときに旧 revision を候補と誤認しないよう、上の例のように毎回新しい値を指定してください。未指定時は checkout 済みSHAをfallbackとして使います。`/api/config` は既存フィールドを維持し、`DEPLOYMENT_VERSION` が設定された revision だけ `deployment_version` も返します。これにより、初回導入時の旧 revision も同じ probe に 200 を返しつつ、revision 名や非公開 URL を workflow log に出さず、本番 traffic が候補まで到達したことを確認できます。各 probe は cache 回避用の query を付けます。

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

- `CI` の `quality_gate` 成功後、`ci.yml` の `deploy_production` job が local reusable workflow を `target_sha=${{ github.sha }}`、`ci_run_id=${{ github.run_id }}` で呼び出します。必要な `CLOUD_RUN_ENV_FILE_BASE64` は workflow_call へ明示的に渡します。called workflow は caller の ref / SHA / workflow 名と、GitHub API の run metadata（`name=CI`、`event=push`、`head_branch=main`、実行中）を照合し、同じrunの jobs API で canonical `Quality gate (selected checks)` の completed/success を再確認します。これにより production jobs は CI と同じ Actions check suite に表示され、別の `workflow_run` deploy は作られません。
- CI workflow identity は固定 path `.github/workflows/ci.yml` と、live repository の API で解決した immutable workflow ID `187172373` を照合します。workflowを再作成してIDが変わった場合は、この定数を明示的に更新してから再開します。
- 手動の break-glass 実行は trusted `main` ref からのみ起動でき、必須入力 `target_sha` と任意の boolean input `identity_exchange_only` を受け取ります。completed状態の候補runをGitHub APIで取得し、同一 SHA の `CI` push・main・completed runを1件確定した後、同じrunの canonical `Quality gate (selected checks)` が completed/success であることを検証してから後続 job へ進みます。自動 deploy failure で CI run 全体の conclusion が failure になっていても、Quality gate が成功していれば手動 retry の候補にできます。
- `identity_exchange_only=true` の手動実行は `verify-target` を必ず通過した後、`production` environment の `verify-deploy-identity` で deploy 用 WIF の入力検証と、credentials fileを作らない pinned auth の `token_format: access_token` によるOIDC→Google access token exchangeだけを確認します。checkout、build、production env materialize、deploy、API write、traffic 操作は行わず、通常の deploy job と cutover guard は実行しません。
- 通常の自動／手動 deploy は `authorize-deploy-cutover` が repository variable `PRODUCTION_DEPLOY_ENABLED` の文字列 `true` を fail-closed に確認した場合だけ進みます。通常の production 経路を許可するまで `verify-target` の CI / Quality gate 契約は変わりません。
- checkout は検証済み対象 SHA に固定し、checkout 後の `git rev-parse HEAD` との一致を assert します。
- 自動／手動の全 production release は、旧 `workflow_run` と評価済み group が一致する固定の `deploy-production-Deploy to production` concurrency group に入り、`cancel-in-progress=false` です。同一 group では実行中を1件、pendingを最大1件だけ保持し、新しい queued run が古い pending run を置き換えます。進行中の production deploy は取消されません。CI 側は PR / develop の stale run を取消できますが、main push の CI run は run ID 固有 group のため相互に取消しません。candidate tag、traffic、rollback操作を同時に進めません。
- PR / develop push では `deploy_production` jobをskipし、本番 deploy jobを作りません。
- Cloud Run は traffic 0% の候補作成、tag URL の health check、10% canary、60 秒の継続確認、100% 昇格の順に進みます。canary 失敗時は直前の traffic 配分へ自動復旧します。
- Cloud Run の minimum instances は repository variable `CLOUD_RUN_MIN_INSTANCES` で上書きできます。未設定時は紹介用 URL の初回体験を優先して `1` を使います。費用優先へ戻す場合は `0` を設定します。
- Reader文章インポートなどレスポンス後も継続する非同期ジョブのため、デプロイ環境ファイルでは `CLOUD_RUN_NO_CPU_THROTTLING=true` を設定します。`false` のままでは202応答後にバックグラウンド処理が停止し得ます。

### GitHub Actions の WIF 設定

repository variables（秘密ではない値）を、WIF variables は deploy と preflight の両 workflow から参照できる範囲へ、build service account は `build-backend-artifact` job だけが参照できる範囲へ登録します。

| Variable | 用途 |
|---|---|
| `GCP_PROJECT_ID` | 本番 GCP project ID |
| `GCP_DEPLOY_WIF_PROVIDER` | production deploy 用の full Workload Identity Provider resource name |
| `GCP_PREFLIGHT_WIF_PROVIDER` | authenticated preflight 用の full Workload Identity Provider resource name |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | production deploy provider が impersonate する service-account email |
| `GCP_BUILD_SERVICE_ACCOUNT` | `build-backend-artifact` が Cloud Build に明示する dedicated build service-account email（秘密ではない値） |
| `GCP_PREFLIGHT_SERVICE_ACCOUNT` | authenticated preflight provider が impersonate する read-only service-account email |
| `PRODUCTION_DEPLOY_ENABLED` | 通常の production deploy cutover guard。初期値は `false` とし、許可時だけ文字列 `true` |

repository secret は次のとおりです。

| Secret | 用途 |
|---|---|
| `CLOUD_RUN_ENV_FILE_BASE64` | `.env.deploy` を base64 化した値 |

`PRODUCTION_DEPLOY_ENABLED` は初期値 `false` にします。main へこの変更を反映した後、`identity_exchange_only=true` の手動実行と Production deploy preflight が成功し、deploy service account の IAM disposition が完了するまで `true` に変更しません。これらの外部設定と確認が揃うまでは、通常の自動／手動 production deploy は cutover guard で停止します。

`GCP_BUILD_SERVICE_ACCOUNT` は `build-backend-artifact` job だけが読み、`scripts/build_backend_artifact.sh` が `projects/<PROJECT_ID>/serviceAccounts/<GCP_BUILD_SERVICE_ACCOUNT>` 形式で一度だけのCloud Build submitへ渡します。helperは `git archive TARGET_SHA` のprivate temporary contextだけを送ります。identity-only、authenticated preflight、通常の PR/CI job には build service account を渡しません。通常の PR と deploy 以外の CI job には OIDC 権限を渡さず、CI の `deploy_production` caller jobには called jobsが必要とする `actions:read`、`id-token:write`、`attestations:write`、`contents:read` の unionだけを渡します。identity-only と preflight の OIDC はそれぞれのread-only token exchange / probeに限定します。

`GCP_SA_KEY` と `GCP_SA_PROJECT_ID` は移行後の workflow から参照しません。旧 key は WIF 経路の検証が完了するまで無効化・削除せず、workflow に自動 fallback を追加しないでください。

外部設定は次の順に準備します。ここに書く placeholder は実値へ置き換え、実値をこのリポジトリへコミットしません。

1. `deploy_cloud_run.sh`、Firestore Admin API、Firebase Hosting API、Cloud Run promotion、Cloud Build が実際に呼ぶ API と、deploy service account の IAM 権限を inventory します。Cloud Build の dedicated service account については `roles/logging.logWriter` と build が実際に必要とする Artifact Registry / Storage 権限を分離して確認します。preflight は Firestore index list と Firebase Hosting release list だけを呼ぶため、その read-only service account の権限を分けて確認します。repository の role 一覧は候補であり、live IAM の証拠ではありません。
2. Google Cloud に Workload Identity Pool と deploy / preflight それぞれの OIDC provider を作成します。issuer は `https://token.actions.githubusercontent.com/` とし、共通の claim を次のように mapping します。

   ```text
   google.subject=assertion.sub,
   attribute.repository_id=assertion.repository_id,
   attribute.repository_owner_id=assertion.repository_owner_id,
   attribute.ref=assertion.ref,
   attribute.workflow=assertion.workflow,
   attribute.workflow_ref=assertion.workflow_ref
   ```

   deploy provider にだけ `attribute.environment=assertion.environment` と optional な `attribute.job_workflow_ref='job_workflow_ref' in assertion ? assertion.job_workflow_ref : ''` を追加します。manual direct token には `job_workflow_ref` claim がないため空文字へ fallbackし、CI reusable auto の tokenだけ mapped attributeを exact照合します。authenticated preflight job は GitHub environment を参照しないため、preflight provider では存在しない `environment` claim を mapping しません。

3. provider の attribute condition は repository 名だけに頼らず、numeric ID、main ref、workflow identity へ限定します。production deploy provider の例は次のとおりです。

   ```text
   assertion.repository_id == '<REPOSITORY_ID>' &&
   assertion.repository_owner_id == '<REPOSITORY_OWNER_ID>' &&
   assertion.ref == 'refs/heads/main' &&
   assertion.environment == 'production'
   ```

   手動 dispatch の deploy job は `workflow_ref` が deploy workflow 自身です。CI の reusable auto は caller の `workflow_ref` と called job の `job_workflow_ref` をともに固定します。

   ```text
   # manual dispatch
   assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main' &&
   assertion.ref == 'refs/heads/main' &&
   assertion.environment == 'production'

   # CI workflow_call
   assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/ci.yml@refs/heads/main' &&
   attribute.job_workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main' &&
   assertion.ref == 'refs/heads/main' &&
   assertion.environment == 'production'
   ```

   deploy provider の実際の condition は上記二経路のいずれかを許可し、repository ID / owner ID、main ref、production environment を両経路へ共通に要求します。

   ```text
   assertion.repository_id == '<REPOSITORY_ID>' &&
   assertion.repository_owner_id == '<REPOSITORY_OWNER_ID>' &&
   assertion.ref == 'refs/heads/main' &&
   assertion.environment == 'production' &&
   (
     assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main' ||
     (
       assertion.workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/ci.yml@refs/heads/main' &&
       attribute.job_workflow_ref == 'stillshore-chirp/wordpack-for-english/.github/workflows/deploy-production.yml@refs/heads/main'
     )
   )
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

   deploy service account の Cloud Run、Cloud Build submit、Artifact Registry reader、Container Analysis occurrence read、Firestore index、Firebase Hosting の resource role は手順 1 の inventory と実 API の権限エラーを根拠に最小限へ確定します。deploy service account に Artifact Registry writer は付与せず、必要な image read は `roles/artifactregistry.reader` の範囲で確認します。native provenance lookupには project-level `roles/containeranalysis.occurrences.viewer` と `containeranalysis.googleapis.com` が必要です。このAPIの有効化と代表roleの付与は今回のWIF cutover確認で完了しています（実project/service-account識別子は外部設定として非公開）。Cloud Build は `projects/<PROJECT_ID>/serviceAccounts/<GCP_BUILD_SERVICE_ACCOUNT>` を指定し、dedicated build service account には `roles/logging.logWriter` と Artifact Registry writer を想定します。`cloudbuild.backend.yaml` は `options.logging: CLOUD_LOGGING_ONLY` を設定します。build service account の追加 role と実効権限は live IAM inventory で確認します。preflight service account には Firestore index list の `datastore.indexes.list` だけを含む project custom role と、Firebase Hosting の最小の定義済みread-only roleである `roles/firebasehosting.viewer` を付与します。`roles/datastore.viewer` は entity read も含むためpreflightには付与しません。deploy 用の write role（`roles/run.admin`、`roles/cloudbuild.builds.editor`、`roles/datastore.indexAdmin`、`roles/firebasehosting.admin` など）も付与しません。role の適用範囲と実効権限は live IAM inventory で確認します。
5. provider resource name、deploy / preflight / dedicated build の対象 service account email、project ID を上記 variables へ登録し、両 workflow の安全な token exchange と preflight read-only probe を確認します。provider、variables、IAM binding、exchange が準備できるまで、この repository 変更を merge-ready と判断しません。

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
- `roles/artifactregistry.reader`（deploy側のimage readが必要な場合）
- `roles/cloudbuild.builds.editor`
- `roles/datastore.indexAdmin`
- `roles/firebasehosting.admin`
- `roles/containeranalysis.occurrences.viewer`（`--show-provenance` によるnative provenance read）
- `roles/serviceusage.serviceUsageConsumer`（API利用に必要な `serviceusage.services.use` を含み、service の enable/disable 管理権限は含まない）
- `roles/iam.serviceAccountUser`

dedicated Cloud Build service account に必要な代表ロール:

- `roles/logging.logWriter`（`options.logging: CLOUD_LOGGING_ONLY` のログ書き込み）
- `roles/artifactregistry.writer`（Cloud Build が生成 image を Artifact Registry へ push）
- Artifact Registry / Cloud Storage など、実際の build 入出力に必要な resource role（live IAM inventory で確定）

authenticated preflight service account は次の read-only role に限定します。

- `datastore.indexes.list` だけを含む project custom role
- `roles/firebasehosting.viewer`（Hosting resource の read-only access。release list の API 到達性を確認する）

preflight service account に `roles/datastore.viewer`やproduction deploy 用 roleを追加しないことが repository 外部設定の hardening 条件です。safe exchange / read-only probe が不足permissionで失敗した場合だけ、エラーで要求されたpermissionを個別に確認します。

Cloud Build の submit 呼び出しは専用 build service account resource を明示し、project の既定 service account へ暗黙委譲しません。ソースアップロードやログ閲覧には、環境によって Cloud Storage / Cloud Build viewer 系の追加権限が必要です。権限は最小権限を基本とし、広い `roles/viewer` は切り分け目的に限ります。

native provenanceの取得に使う `containeranalysis.googleapis.com` は有効化済みで、deploy service accountへ project-level `roles/containeranalysis.occurrences.viewer` を付与済みです。これはrepository内のplaceholder契約ではなく、今回のWIF cutover時点で確認したlive dispositionです。実値はこの文書へ記録しません。

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
