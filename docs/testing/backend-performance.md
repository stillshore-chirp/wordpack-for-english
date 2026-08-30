# バックエンド性能回帰チェック（p95）

## 目的
主要エンドポイントの p95 応答時間を定期的に計測し、回帰を早期検知します。

## 対象
- `/healthz`
- `/api/word/pack`

## 実行方法（ローカル）
1. 必要に応じて `.env` やテスト用の環境変数を設定します。
2. `pytest` を実行して p95 を確認します。

### 正例（推奨）
```bash
API_P95_THRESHOLD_MS=1500 PYTHONPATH=apps/backend pytest -q --no-cov tests/test_api_performance.py
```

### 負例（閾値が厳しすぎて回帰でなくても落ちる）
```bash
API_P95_THRESHOLD_MS=10 PYTHONPATH=apps/backend pytest -q --no-cov tests/test_api_performance.py
```

## CI 運用
- 週次での回帰検知は [`scheduled-maintenance.yml`](../../.github/workflows/scheduled-maintenance.yml) の `schedule`（全suite）で実行します。手動実行は GitHub Actions の `workflow_dispatch` で `suite=backend-performance` を選択します。
- ステージング/本番前の実行時は `API_P95_THRESHOLD_MS` を環境に合わせて調整してください。

## 環境変数
- `API_P95_THRESHOLD_MS`: p95 の許容値（ミリ秒）。未設定時はテスト内で既定値を使用します。
