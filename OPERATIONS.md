# 運用 SLO・メトリクス・監視

WordPack for English の本番運用で、何を監視し、どの状態を正常・注意・障害として扱い、Cloud Run / Firebase Hosting / Firestore / OpenAI API のどこから復旧するかをまとめる。

この文書の SLO は、外部利用者に対する正式な可用性保証ではなく、個人運用・小規模本番環境での **運用品質目標** として扱う。実トラフィック、コスト、利用者数が変わった場合は、ここにあるしきい値を見直す。

関連文書:

- [README.md](./README.md) - プロダクト概要と最短起動
- [docs/deployment.md](./docs/deployment.md) - Cloud Run / Firebase Hosting / GitHub Actions デプロイ
- [docs/api-reference.md](./docs/api-reference.md) - REST API 一覧
- [docs/authentication.md](./docs/authentication.md) - Google OAuth / セッション / ゲスト認証
- [docs/firestore.md](./docs/firestore.md) - Firestore インデックス、エミュレータ、シード、削除運用
- [docs/infrastructure.md](./docs/infrastructure.md) - Cloud Run / Firebase / Firestore / OpenAI API の構成図
- [docs/testing/backend-performance.md](./docs/testing/backend-performance.md) - p95 性能回帰チェック
- [.github/workflows/ci.yml](./.github/workflows/ci.yml) - PR / main push の CI
- [.github/workflows/deploy-production.yml](./.github/workflows/deploy-production.yml) - 本番デプロイ
- [.github/workflows/production-deploy-preflight.yml](./.github/workflows/production-deploy-preflight.yml) - daily schedule / main手動のread-only deploy probe
- [.github/workflows/scheduled-maintenance.yml](./.github/workflows/scheduled-maintenance.yml) - 週次およびmanual dispatch（`suite`選択）の保守suite

---

## 監視対象の全体像

| レイヤ | 見るもの | 主な確認場所 | 目的 |
|---|---|---|---|
| Frontend / Firebase Hosting | 静的配信、Hosting release、`/api/**` rewrite、ブラウザからの到達性 | Firebase Console、Hosting release history、Hosting web request logs | 画面が開けるか、API rewrite が壊れていないかを確認する |
| Backend / Cloud Run | `/healthz`、request count、latency、5xx、revision、CPU / memory、起動失敗 | Cloud Run console、Cloud Monitoring、Cloud Logging | API が起動していて、遅延・5xx・リソース逼迫がないかを確認する |
| App metrics | `/metrics` の path 別 `p95_ms` / `count` / `errors` / `timeouts` | `GET /metrics`、Cloud Logging | アプリ内で観測した path 別の簡易状態を見る |
| App logs | `request_complete` の JSON ログ、`latency_ms`、`status_code`、`is_error`、`is_timeout`、`request_id` | Cloud Logging | エラー原因、遅い path、失敗リクエストを追跡する |
| Firestore | 読み書きエラー、権限エラー、インデックス不足、レイテンシ、使用量 | Firestore console、Cloud Monitoring、Cloud Logging | 永続化・検索・一覧取得の障害を切り分ける |
| OpenAI API / LLM / TTS | `llm_complete_*`、`tts_*` ログ、rate limit、timeout、TTS 失敗、生成遅延 | Cloud Logging、Langfuse（任意）、OpenAI dashboard / status | 生成・音声読み上げの外部依存障害を切り分ける |
| CI/CD | CI の Quality gate / Static deploy preflight、Deploy to production、Production deploy preflight、Scheduled maintenance、Cloud Build、Firebase deploy | GitHub Actions、Cloud Build、Cloud Run revisions、Firebase release history | 壊れた revision / Hosting release を本番に出していないか確認する |

---

## SLO / しきい値

| 項目 | SLO / 目標 | 注意 | 障害扱い | 備考 |
|---|---:|---:|---:|---|
| `/healthz` 到達性 | 月次 99.0% 以上 | 3 分以上連続失敗 | 15 分以上連続失敗 | Cloud Monitoring の uptime check を作る場合はこの endpoint を対象にする |
| 同期 API p95 | p95 1,500ms 以下 | 10 分以上 p95 1,500ms 超 | 15 分以上 p95 2,000ms 超 | CI のローカル目安は `API_P95_THRESHOLD_MS=1500`、週次回帰は 2,000ms |
| `POST /api/word/pack` 新規生成 | 受付から生成・保存・応答までが成功する | p95 悪化、LLM timeout / retry 増加 | ユーザーが同期リクエスト中に待たされ続ける、または生成不能 | 新規生成は同期処理として扱う。遅延はリクエスト latency に含める |
| 再生成ジョブ | ジョブ受付と完了状態を分けて確認する | 完了待ちが伸びる | ジョブが完了しない、または連続失敗 | README の非同期ジョブ化は再生成向け。受付 latency と完了時間を分けて見る |
| API 5xx 率 | 30 分窓で 1% 以下 | 10 分窓で 2% 超 | 5 分窓で 5% 超 | 4xx は利用者入力・認証状態も含むため、原則 5xx と timeout を優先する |
| `401` 率 | 急増しない | ログイン直後やリリース直後に急増 | 全ユーザーがログイン不能 | アプリ内 metrics では 401 を `is_error=true` として数える。セッション期限切れと本障害を分けて見る |
| Timeout | ほぼ 0 | 15 分で 3 件以上 | 15 分で 10 件以上、または TTS / 生成が連続失敗 | Cloud Run timeout、Firestore、OpenAI API のどこで詰まったかを見る |
| Firestore 読み書き | 主要 API で保存・検索が成功 | index / permission / unavailable が出る | WordPack 保存・検索が継続不能 | Firestore フォールバックは一部処理を継続させる安全策であり、障害を隠す目的ではない |
| OpenAI API / TTS | 生成・TTS が成功し、UI に回復可能なエラーが出る | rate limit / timeout が増える | 生成・TTS が継続不能 | `request_complete` だけでなく `llm_complete_*` / `tts_*` の event を見る |
| 本番デプロイ | 10% canary の 60 秒 health check 後に 100% 昇格し、`Deploy to production` が成功 | canary 中または昇格後に latency / 5xx が悪化 | 新 revision で health check 失敗、または主要導線が壊れる | canary 失敗時は自動 rollback。昇格後は直前の healthy revision へ手動 rollback する |

---

## アプリ内で既に出しているシグナル

### `/healthz`

`GET /healthz` はライブネス / レディネス確認用の簡易 endpoint。正常時は次を返す。

```json
{"status":"ok"}
```

確認例:

```bash
curl -fsS https://<api-host>/healthz
```

### `/metrics`

`GET /metrics` はコンテナ内メモリに保持している rolling metrics を返す。

```json
{
  "paths": {
    "/api/word/pack": {
      "p95_ms": 123.45,
      "count": 20,
      "errors": 0,
      "timeouts": 0
    }
  }
}
```

注意点:

- `p95_ms` は path 別の rolling latency。
- `errors` は middleware が `is_error=true` と判断した回数。現状は例外、5xx、401 を含む。
- `timeouts` は timeout 例外として捕捉できた回数。
- in-memory なので、Cloud Run の instance / revision 再起動でリセットされる。
- 複数 instance では instance ごとの値になるため、長期・全体集計は Cloud Logging / Cloud Monitoring を正とする。

### 構造化アクセスログ

各リクエスト完了時に `request_complete` を JSON 形式で出す。主に見る field は次の通り。

| field | 意味 |
|---|---|
| `path` / `method` | 対象 endpoint |
| `latency_ms` | アプリ middleware が観測した処理時間 |
| `status_code` | HTTP status |
| `is_error` | middleware がエラー扱いしたか |
| `is_timeout` | timeout 扱いしたか |
| `error_type` / `error_message` | 例外や 5xx / 401 の概要 |
| `request_id` | 1 リクエストの追跡 ID |
| `trace` / `spanId` | Cloud Trace 連携用 field（`x-cloud-trace-context` がある場合） |

Cloud Logging での基本クエリ例:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
jsonPayload.event="request_complete"
```

5xx / 401 / 例外を含むアプリ内エラーを見る例:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
jsonPayload.event="request_complete"
jsonPayload.is_error=true
```

遅いリクエストを見る例:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
jsonPayload.event="request_complete"
jsonPayload.latency_ms>=1500
```

OpenAI / LLM / TTS まわりの失敗を探す例。`request_complete` は HTTP 5xx を `HTTP502` のような一般値に丸めるため、LLM/TTS 専用 event を優先して検索する。

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
(
  jsonPayload.event="llm_complete_error"
  OR jsonPayload.event="llm_complete_failed_all_retries"
  OR jsonPayload.event="tts_request_failed"
  OR jsonPayload.event="tts_client_unavailable"
  OR jsonPayload.event="tts_stream_error"
  OR (jsonPayload.event="request_complete" AND jsonPayload.status_code>=500)
  OR (jsonPayload.event="request_complete" AND jsonPayload.status_code=429)
)
```

rate limit / auth / timeout を分ける例:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
(
  jsonPayload.reason=~"rate_limit|authentication_error|connection_error|api_status_error|api_error"
  OR jsonPayload.error_type=~"RateLimit|Timeout|Authentication|API|FuturesTimeout"
  OR jsonPayload.error=~"rate limit|timeout|429|401|invalid api key"
)
```

Firestore まわりの失敗を探す例:

```text
resource.type="cloud_run_revision"
resource.labels.service_name="wordpack-backend"
(
  jsonPayload.error_message=~"Firestore|firestore|index|permission|unavailable"
  OR jsonPayload.error=~"Firestore|firestore|index|permission|unavailable"
  OR textPayload=~"Firestore|firestore|index|permission|unavailable"
)
```

---

## Cloud Run で見るもの

Cloud Run は Backend の一次切り分け場所。特に次を見る。

| 観点 | 何を見るか | 判断 |
|---|---|---|
| traffic / 5xx | request count を response code class で分解 | 5xx が増えていれば backend / dependency / config を疑う |
| latency | request latency p50 / p95 / p99 | p95 が 1,500ms を超え続けるなら遅延調査 |
| pending latency | pending request latency | instance 起動待ち、concurrency、cold start、max instance 到達を疑う |
| revision | 最新 revision、traffic split、deploy time | デプロイ直後に悪化したら rollback 候補 |
| resource | CPU / memory utilization、container restart | OOM、CPU 飽和、設定不足を疑う |
| logs | `request_complete`、起動時 config validation error | 起動不能、secret 不足、allowed host / CORS 設定ミスを疑う |

確認コマンド例:

```bash
gcloud run services describe wordpack-backend \
  --project <project-id> \
  --region asia-northeast1

gcloud run revisions list \
  --service wordpack-backend \
  --project <project-id> \
  --region asia-northeast1
```

---

## Firebase Hosting で見るもの

Firebase Hosting は Frontend と `/api/**` rewrite の確認場所。

| 観点 | 何を見るか | 判断 |
|---|---|---|
| Hosting release | 最新 release、直近 deploy の成否 | フロントだけ壊れた場合は release rollback を検討 |
| rewrite | `firebase.json` の `/api/**` が Cloud Run へ向いているか | API だけ 404 / 502 なら rewrite / backend 到達性を疑う |
| request logs | static asset の 4xx / 5xx、`/api/**` の異常 | Cloud Logging 連携済みなら request log を見る |
| domain / TLS | 独自ドメイン、証明書、`.web.app` 到達性 | ブラウザから画面が開けない場合に確認 |

復旧は、Hosting release history から直前の正常 release へ戻すか、`main` の既知正常 commit から再デプロイする。

```bash
firebase deploy --only hosting --project <firebase-project-id>
```

---

## Firestore で見るもの

Firestore は WordPack、例文、記事、ユーザー設定の永続化に使う。

| 観点 | 何を見るか | 判断 |
|---|---|---|
| read / write / delete usage | 急増、quota 逼迫 | ループ、過剰 polling、誤った bulk 操作を疑う |
| latency / API errors | unavailable、deadline、permission denied | GCP 側障害、IAM、security rules、service account を疑う |
| indexes | composite index の未反映・不足 | 一覧、検索、集計が失敗する場合に確認 |
| data shape | `word_packs` / `examples` / `articles` の schema | 手動修正や移行の副作用を疑う |

インデックス同期の復旧例:

```bash
firebase deploy --only firestore:indexes --project <firebase-project-id>
```

本番では `FIRESTORE_EMULATOR_HOST` を設定しない。設定されていると Cloud Firestore ではなく emulator へ向かうため、本番データが読めない。

---

## OpenAI API / Langfuse で見るもの

生成来歴と通常CIの無料評価の全体手順は [docs/llmops/](docs/llmops/index.md) を参照する。production 既定では raw prompt / output を送らず、保存済み provenance の `request_id` / `workflow_id` / `trace_id`、`release` / `git_sha` / `cloud_run_revision`、`prompt_revision` を private log と相関する。

OpenAI API は WordPack 新規生成、再生成、TTS の外部依存。アプリ単体の uptime が正常でも、ここが落ちると生成・音声読み上げだけが失敗する。

| 観点 | 何を見るか | 判断 |
|---|---|---|
| auth | `tts_request_failed` の `reason=authentication_error`、LLM 側の `AUTH`、401 / 403 | key の誤設定、失効、環境変数の未反映を疑う |
| rate limit | `reason=rate_limit`、`RATE_LIMIT`、HTTP 429、rate limit message | 利用量、モデル別上限、急増 traffic を疑う |
| timeout | `is_timeout=true`、`llm_complete_error` / `llm_complete_failed_all_retries` の timeout | 外部 API 遅延、Cloud Run timeout、`LLM_TIMEOUT_MS` を確認 |
| trace | Langfuse trace、span duration、error metadata | どの生成処理で遅い・失敗したかを追う |
| cost / usage | OpenAI usage dashboard | 想定外の利用増、TTS 連打、再生成ループを確認 |

対応の優先度:

1. OpenAI status と dashboard で外部障害・rate limit・billing を確認する。
2. Cloud Logging で `llm_complete_*` / `tts_*` event、`reason`、`error_type`、`request_id` を見る。
3. Langfuse 有効時は同じ request / span を辿る。
4. 401 / 403 / authentication の場合のみ key / secret を確認する。rate limit や timeout だけで key を不用意に rotate しない。
5. 外部障害の場合は生成・TTS の再試行を控え、閲覧機能への影響がないことを確認する。

---

## CI / CD で見るもの

| ワークフロー | 目的 | 失敗時の見方 |
|---|---|---|
| `CI` | classifierが選択するbackend / frontend / container / deploy / governance / workflow contract / Playwright、security text scan、Quality gate | PR ではここが最低限の品質ゲート |
| `Production deploy preflight` | daily schedule またはmain refの手動実行で、gcloud / Firestore / Firebase Hostingのread-only probe | credential欠如またはprobe失敗を本番デプロイ前の設定・接続問題として確認する |
| `Scheduled maintenance` | 週次またはsuite選択の手動実行で、CodeQL / OpenSSF Scorecard / backend performance / 全Playwright回帰を検査 | suite単位で保守上の回帰を切り分ける |
| `Deploy to production` | CI main push の `quality_gate` 後に呼ばれる reusable workflow、またはmain手動実行。`verify-target` / `authorize-deploy-cutover` の後、`prepare-release-artifacts`、`build-backend-artifact`、`attest-backend-artifact`、`deploy` に分離したfrontend準備、backend build-once、digest/native provenance/SBOM/attestation検証、`.env.deploy` 復元、Cloud Run traffic 0% 候補、10% canary と自動 rollback、100% 昇格、Firebase Hosting deploy | 本番リリース失敗時の一次ログ。停止したjob、digest不一致、証明書不一致、自動 rollback の成否を確認する |
| Cloud Build / Artifact Registry | `cloudbuild.backend.yaml` で `git archive TARGET_SHA` のprivate contextを一度だけbuildし、manifest digestとnative provenanceを保持 | build resultとregistry digestが一致するか、failed tag / manifestのcleanupと保持期限を確認 |

### 本番 workflow の認証運用

`Deploy to production` は `CI` の `quality_gate` 後に `target_sha=${{ github.sha }}` と `ci_run_id=${{ github.run_id }}` を受け取る reusable workflow、またはmain手動実行として、`GCP_DEPLOY_WIF_PROVIDER` から `GCP_DEPLOY_SERVICE_ACCOUNT` を impersonate します。`Production deploy preflight` は別の `GCP_PREFLIGHT_WIF_PROVIDER` から `GCP_PREFLIGHT_SERVICE_ACCOUNT` を impersonate します。workflow は `GCP_PROJECT_ID`、4つの WIF repository variables、`build-backend-artifact` jobだけの `GCP_BUILD_SERVICE_ACCOUNT` を参照し、`GCP_SA_KEY` や `credentials_json` への fallback を持ちません。dedicated build service account はbuild job内のCloud Build buildにだけ使い、deploy helperは検証済みの完全な `IMAGE_URI`（`@sha256:<64-hex>`）を消費して再buildしません。Artifact Registry writer は dedicated build service account、deploy service account は必要な image read の `roles/artifactregistry.reader` に分離します。Cloud Build config は `options.logging: CLOUD_LOGGING_ONLY` を使い、dedicated build service account には `roles/logging.logWriter` を想定します。通常の production deploy は `PRODUCTION_DEPLOY_ENABLED` が文字列 `true` のときだけ `authorize-deploy-cutover` を通過します。初期値は `false` とし、main merge後の `identity_exchange_only=true` による deploy identity exchange、Production deploy preflight、deploy service account と dedicated build service account の IAM disposition が完了するまで有効化しません。

OIDC の `id-token: write` は `build-backend-artifact`、`attest-backend-artifact`、`deploy`、authenticated preflight、manual main の identity-only jobそれぞれの job scope に限定されます。CI の `deploy_production` caller jobには called jobsの権限 unionを渡しますが、通常の PR job / runner と `verify-target` / `prepare-release-artifacts` / `authorize-deploy-cutover` には追加しません。build jobはCloud Build、attest jobはGitHub attestation、deploy jobはprivate GAR検証とreleaseのために使います。対象 SHA の CI / Quality gate 検証、Cloud Run の canary・health check・自動 rollback、materialized env file の cleanup は既存契約として維持します。identity-only job は pinned auth action の `token_format: access_token` によるWIF token exchangeと、その `access_token` 出力が非空であることの確認だけを実行し、tokenを表示・保存せず、checkout/build/env materialize/deploy/API write/traffic操作を行いません。

provider の numeric repository / owner ID、main ref、manual deploy の exact `workflow_ref`、CI reusable auto の caller `workflow_ref` と deploy `job_workflow_ref`、deploy 側の `production` environment 条件、`roles/iam.workloadIdentityUser` binding、deploy service account の実効 resource role、dedicated build service account の `roles/logging.logWriter` と build入出力 role、preflight service account の `datastore.indexes.list` だけのcustom role / `roles/firebasehosting.viewer`、GitHub environment protection、token exchange は外部設定です。repository の静的検査と focused test はこれらの live 設定や本番 probe の成功を証明しないため、merge 前に [docs/deployment.md](./docs/deployment.md) の順序で inventory と exchange を確認します。preflight は Firestore index list と Firebase Hosting release list だけを probe する read-only job とし、`roles/datastore.viewer`やdeploy 用の write roleを付与しません。identity-only、preflight、通常のPR/CI jobには `GCP_BUILD_SERVICE_ACCOUNT` を渡しません。

本番デプロイ前のローカル dry-run:

```bash
./scripts/deploy_cloud_run.sh \
  --dry-run \
  --env-file .env.deploy \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend \
  --image-uri <region>-docker.pkg.dev/<project-id>/wordpack/backend@sha256:<64-hex>
```

### backend artifact の不一致と失敗時 cleanup

既存 `Deploy to production` workflowのartifact順序は、`prepare-release-artifacts` のtarget SHA checkout / frontend build → `build-backend-artifact` の `git archive TARGET_SHA` によるprivate temporary context・Cloud Build一度だけ・build result / Artifact Registry manifest digest照合・同digestのcontainer `/healthz` smoke → 検証済みregistry digest imageからtarget SHAのdeterministicなlocal handoff tagを作り、同じimage IDを確認してarchive SHA-256をhandoff → `attest-backend-artifact` のarchive checksum検証・tag復元・checksum-pinned Syft 1.51.1 SPDX 2.3生成・project-owned custom delivery provenanceとSBOMの作成 → `deploy` のGCP再認証後private GAR向け `gh attestation verify` → digest-only Cloud Run deployです。Cloud Build native provenance は reserved SLSA predicate `https://slsa.dev/provenance/v1` として `gcloud artifacts docker images describe <image>@<digest> --show-provenance --format=json` でexact digestから取得し、image digest、GoogleHostedWorker、invocation、`_SOURCE_REPOSITORY` / `_TARGET_SHA` / `_BUILDER_WORKFLOW` substitutionsを検証します。local archive submitでSCM metadataが省略される場合は受け入れ、存在する場合はrepository/ref/SHAを厳密照合します。検証済みJSONのSHA256を `nativeProvenanceSnapshotSha256` としてproject-owned custom delivery predicate `https://github.com/stillshore-chirp/wordpack-for-english/attestations/backend-delivery/v1`へ結合します。Syft 1.51.1は復元したlocal handoff tagを入力にし、actions/attestのsubjectとCloud Run deployは同じimmutable registry digestを使います。Anchore Actionは使用しません。GitHub attestation のdelivery predicate `runDetails.builder.id` は exact deploy `BUILDER_WORKFLOW` URI、payload内の `buildDefinition.buildType` は `${BUILDER_WORKFLOW}#backend-cloud-build-v1` とし、`underlyingBuilder=https://cloudbuild.googleapis.com/GoogleHostedWorker` と `cloudBuildProvenance=required` は上流のCloud Build native provenanceとの対応を示す値として照合します。GitHub署名者identityがGoogle builder identityを示すわけではありません。Cloud Build native provenance は `cloudbuild.backend.yaml` の `options.requestedVerifyOption: VERIFIED` でも独立して要求します。expected repository、signer workflow、source ref、source digest、signer digest、target SHA、builder、digest、SBOMの存在を一つでも確認できなければ、Cloud Run、traffic、Hostingのwriteへ進めません。新しいworkflowは追加せず、通常PRからpublishしません。job追加はjob-wide OIDC/permissionsと依存tool隔離、credential cleanup、artifact handoffを保つための既存workflow内の分割です。

Cloud Buildへのsource uploadは、archived target SHA内の明示的な `.gcloudignore` allowlistを使います。Dockerfile、build config、requirements、backend runtime source以外のtracked env、credential、generated fileもstagingへ送らず、native provenanceではSCM `buildConfigSource` または空でないinline `buildConfig` のどちらか一方を必須にします。

運用時の確認例（対象SHAをcheckout済みのtreeで実行し、識別子は必ず実環境の値へ置き換える）:

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
export SOURCE_DIGEST="<40-char-github.sha>"
export SIGNER_DIGEST="<40-char-github.workflow_sha>"
gh attestation verify "oci://${IMMUTABLE_IMAGE}" \
  --repo "<owner>/<repository>" \
  --signer-workflow "<owner>/<repository>/.github/workflows/<trusted-workflow>.yml" \
  --source-ref refs/heads/main \
  --source-digest "${SOURCE_DIGEST}" \
  --signer-digest "${SIGNER_DIGEST}" \
  --predicate-type https://github.com/stillshore-chirp/wordpack-for-english/attestations/backend-delivery/v1

gh attestation verify "oci://${IMMUTABLE_IMAGE}" \
  --repo "<owner>/<repository>" \
  --signer-workflow "<owner>/<repository>/.github/workflows/<trusted-workflow>.yml" \
  --source-ref refs/heads/main \
  --source-digest "${SOURCE_DIGEST}" \
  --signer-digest "${SIGNER_DIGEST}" \
  --predicate-type https://spdx.dev/Document/v2.3
IMAGE_URI="${IMMUTABLE_IMAGE}" make release-cloud-run \
  PROJECT_ID="<project-id>" REGION="<region>" ENV_FILE=".env.deploy" \
  NO_TRAFFIC=true TRAFFIC_TAG=candidate
```

`--source-digest` はattestation certificateのsource repository digest（workflowの `github.sha`）です。`--signer-digest` は署名workflow fileのrevision（workflowの `github.workflow_sha`）です。Cloud Buildの対象 `TARGET_SHA` はcustom delivery predicateの `targetSha` と `resolvedDependencies[].digest.gitCommit` で別に固定します。helperの出力はimage name/URI/digestと `native_provenance_snapshot_sha256` だけで、Cloud Build build IDを公開しません。build jobは検証済みregistry digest imageをtarget SHAのlocal handoff tagへ付け替え、同じimage IDを確認してarchive SHA-256を渡します。Syft 1.51.1はattest runnerでarchive checksumを確認して復元したlocal handoff tagを入力にし、actions/attestのsubjectとCloud Run deployはimmutable registry digestを使います。Google credentialはSBOM・attestation前にcleanupしてdeploy直前に再認証します。

native provenance取得に必要な `containeranalysis.googleapis.com` は有効化済みで、deploy service accountには project-level `roles/containeranalysis.occurrences.viewer` を付与済みです。実projectやservice accountの識別子は公開しません。

build resultとregistry digestの不一致、native provenance欠落、SBOM欠落、attestationのidentity / subject digest不一致は、最初に検出したjob/stepを一次ログへ残して停止します。失敗時は各jobが生成env、workspace、private archive、一時SBOM、credentialをcleanupし、rollback窓に必要なhealthy revision・digestは保持します。frontend release、backend image archive、attestation metadataのGitHub Actions artifactは各1日だけ保持します。failed image/tagやCloud Buildログの保持・削除はArtifact Registry / Cloud Loggingの外部retention policyとowner（release operator）が決めます。GitHub attestationのrepository API storageの保持・削除可否も外部設定として確認します。追加job、artifact転送、Cloud Build、Syft実行によるrunner wall time、Cloud Build時間、registry/GitHub storage増加はIssue/PRのriskとして記録します。release operatorが全体の一次failure ownerで、build/IAMはbuild担当、SPDX/attestationはsecurity/release担当、Cloud Run/Hosting/canary/rollbackはdeploy担当が切り分けます。

job分離のsunsetまたはdemotionは自動で行いません。承認済みリリースの安定実績、1日artifact cleanup、runner/Cloud Build quota/GitHub・Artifact Registry storageの測定、job-wide OIDCと依存tool隔離が不要になったことをIssue/PRで証跡化し、digest、source/signer/target境界、attestation、rollback、credential cleanupを保った設計へ置換できる場合だけ変更します。Syft、native provenance、GitHub attestationの失敗が続く場合は `PRODUCTION_DEPLOY_ENABLED` を無効化してfail closedとし、検証を省略するdemotionは行いません。DependabotのActions更新後はfull SHA pin、attestation scope、SBOM入力、1日retentionをworkflow contractで再確認します。

---

## 障害時の初動フロー

1. **影響範囲を分ける。** 画面が開けない、API が落ちている、保存だけ失敗、生成/TTS だけ失敗、ログインだけ失敗、のどれかを切る。
2. **直近変更を確認する。** GitHub Actions の `Deploy to production`、Cloud Run revision、Firebase Hosting release を見る。
3. **外部依存を確認する。** Google Cloud status、Firebase status、OpenAI status、OpenAI dashboard を見る。
4. **Cloud Run logs を見る。** `request_complete` の `status_code` / `is_error` / `error_type` / `latency_ms` / `request_id` と、LLM/TTS の専用 event を確認する。
5. **復旧策を選ぶ。** 新 revision 起因なら rollback、設定ミスなら env 修正 + redeploy、Firestore index なら index 同期、OpenAI 側なら閲覧機能の健全性確認と再試行抑制。
6. **復旧確認をする。** `/healthz`、主要画面、保存済み WordPack 一覧、WordPack 詳細、生成、再生成ジョブ、TTS のうち影響範囲に応じて確認する。
7. **事後記録を残す。** 発生時刻、検知方法、影響、原因、復旧操作、再発防止を Issue / PR / 運用メモに残す。

---

## 復旧手順

### Cloud Run の新 revision が壊れた

通常の GitHub Actions リリースでは、10% canary の確認に失敗するとデプロイ前の traffic 配分へ自動で戻る。workflow log で `Previous traffic allocation restored` を確認する。`Automatic traffic rollback failed` が出た場合、または 100% 昇格後に問題を検知した場合は、次の手動手順を使う。

1. 直前の healthy revision を確認する。

```bash
gcloud run revisions list \
  --service wordpack-backend \
  --project <project-id> \
  --region asia-northeast1
```

2. traffic を直前 revision へ戻す。

```bash
gcloud run services update-traffic wordpack-backend \
  --to-revisions <healthy-revision-name>=100 \
  --project <project-id> \
  --region asia-northeast1
```

3. `/healthz` と主要 API を確認する。

```bash
curl -fsS https://<api-host>/healthz
curl -fsS https://<api-host>/metrics
```

### Firebase Hosting の release が壊れた

1. Firebase Console の Hosting release history で直前 release を確認する。
2. 直前 release へ rollback する。
3. `/api/**` rewrite が Cloud Run に向いているか確認する。
4. 画面表示、ログイン導線、主要ページ遷移を確認する。

### Firestore index / 権限 / 接続が壊れた

1. Cloud Logging で Firestore 関連 error を検索する。
2. `FIRESTORE_PROJECT_ID`、service account、IAM、`FIRESTORE_EMULATOR_HOST` の混入を確認する。
3. index 不足なら同期する。

```bash
firebase deploy --only firestore:indexes --project <firebase-project-id>
```

4. WordPack 一覧、詳細、保存、例文一覧を確認する。

### OpenAI API が不安定

1. OpenAI status / dashboard で障害、rate limit、billing、モデル availability を確認する。
2. Cloud Logging で `llm_complete_error`、`llm_complete_failed_all_retries`、`tts_request_failed`、`tts_stream_error` を確認する。
3. `request_complete` は HTTP status と latency の全体像として使い、OpenAI 固有原因は LLM/TTS 専用 event で補う。
4. Langfuse 有効時は該当 trace の duration と error metadata を見る。
5. 401 / 403 / authentication の場合は secret と Cloud Run env の反映を確認する。
6. rate limit / timeout の場合は、生成・TTS の連続操作を控え、閲覧・Firestore 保存に影響がないことを確認する。

---

## 推奨アラート

現時点では、このリポジトリに Cloud Monitoring alert policy の IaC はない。運用時は次を Cloud Monitoring / GitHub Actions 通知 / 手動 dashboard で設定する。

| アラート | 条件 | 優先度 |
|---|---|---|
| Uptime check | `/healthz` が 3 分連続失敗 | P1 |
| Cloud Run 5xx | 5xx 率が 5 分で 5% 超 | P1 |
| Cloud Run latency | p95 が 15 分で 2,000ms 超 | P2 |
| App timeout | `jsonPayload.is_timeout=true` が 15 分で 10 件以上 | P1 |
| Firestore error | index / permission / unavailable が deploy 後に発生 | P1 / P2 |
| OpenAI API error | `llm_complete_*` / `tts_*` の rate limit / timeout / 5xx が 15 分で急増 | P2 |
| Deploy failure | `Deploy to production` が失敗 | P1 |
| Performance regression | `Scheduled maintenance` の `backend-performance` suite が失敗 | P2 |

---

## 既知の制約と次の改善候補

- `/metrics` は in-memory で、Cloud Run instance / revision ごとに値が分かれる。長期保存・全体集計には Cloud Monitoring / Cloud Logging の dashboard が必要。
- Cloud Monitoring の dashboard / alert policy はまだコード管理されていない。Terraform または Monitoring API の JSON 定義で管理すると再現性が上がる。
- 新規 WordPack 生成は現状同期 API なので、生成完了までの時間が request latency に入る。生成をジョブ化する場合は、受付 latency / queue wait / completion / failure を dedicated metrics として追加する。
- 再生成ジョブの queue / completion / failure は、運用 dashboard 上では Cloud Logging とアプリログに依存する。専用 metrics を追加すると LLM 障害の検知が早くなる。
- OpenAI の利用量・費用は Cloud Monitoring に自動集約していない。必要なら Langfuse / OpenAI usage export / カスタム metrics のいずれかで補う。
- 401 を app error として数えているため、ログイン状態の揺らぎと backend 5xx を dashboard 上で分ける必要がある。

---

## 参照

- [Cloud Run monitoring](https://cloud.google.com/run/docs/monitoring)
- [Cloud Run metrics list](https://cloud.google.com/monitoring/api/metrics_gcp_p_z#gcp-run)
- [Cloud Logging query language](https://cloud.google.com/logging/docs/view/logging-query-language)
- [Cloud Firestore monitoring](https://cloud.google.com/firestore/docs/monitor-usage)
- [Firebase Hosting web request logs and metrics](https://firebase.google.com/docs/hosting/web-request-logs-and-metrics)
- [OpenAI API error codes](https://platform.openai.com/docs/guides/error-codes/api-errors)
- [OpenAI status](https://status.openai.com/)
- [Google Cloud status](https://status.cloud.google.com/)
- [Firebase status](https://status.firebase.google.com/)
