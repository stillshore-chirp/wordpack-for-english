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
- [.github/workflows/perf-backend.yml](./.github/workflows/perf-backend.yml) - 週次 p95 回帰チェック

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
| CI/CD | CI 成功、Cloud Run config guard、Deploy to production、Cloud Build、Firebase deploy | GitHub Actions、Cloud Build、Cloud Run revisions、Firebase release history | 壊れた revision / Hosting release を本番に出していないか確認する |

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
| `CI` | backend / frontend / security headers / Playwright smoke / Cloud Run dry-run | PR ではここが最低限の品質ゲート |
| `Backend performance regression` | `/healthz` と `/api/word/pack` の p95 回帰検知 | 週次または手動で latency regression を見る |
| `Deploy to production` | `.env.deploy` 復元、設定検証、Cloud Run traffic 0% 候補、10% canary と自動 rollback、100% 昇格、Firebase Hosting deploy | 本番リリース失敗時の一次ログ。自動 rollback の成否も確認する |
| Cloud Build | backend image build と GitHub Checks 連携 | Dockerfile / dependency / Artifact Registry 問題を確認 |

本番デプロイ前のローカル dry-run:

```bash
./scripts/deploy_cloud_run.sh \
  --dry-run \
  --env-file .env.deploy \
  --project-id <project-id> \
  --region asia-northeast1 \
  --service wordpack-backend
```

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
| Performance regression | `Backend performance regression` が失敗 | P2 |

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
