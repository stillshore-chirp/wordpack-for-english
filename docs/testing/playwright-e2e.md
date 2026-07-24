# Playwright E2E テスト

## 目的
- フロントエンドとバックエンドを同時に起動し、主要導線の回帰を E2E で確認します。
- 失敗時は trace / screenshot / video を保存し、原因解析を容易にします。
- 主要シナリオでは axe を用いたアクセシビリティ違反ゼロを検証します（`waitForLoadState` 後に実行）。

## E2E とビジュアル回帰の責務分担
- **E2E（機能）**: 主要導線の「操作 → 結果」を検証し、API 連携や状態遷移の回帰を検知します。
- **ビジュアル回帰（見た目）**: UI の配置・余白・表示崩れなど見た目の差分を検知し、機能が同じでも視覚的な劣化を拾います。
- 役割が重なる場合は、**機能差分は E2E**、**見た目の差分はビジュアル回帰**に寄せて、テストの意図を明確に分離します。

## 前提
- Node.js 22+ と Python 実行環境が利用できること。
- Firestore エミュレータを使う場合は、別ターミナルで起動しておくこと。

## 実行方法

### 正例（ローカルでフル起動）
```
E2E_BASE_URL=http://127.0.0.1:5173 npm run e2e
```

### 負例（依存サーバ未起動のまま実行）
```
npm run e2e
# → webServer の起動やヘルスチェックに失敗し、テストが開始できない
```

## 成果物
- HTML レポート: `playwright-report/`
- 失敗時の trace / screenshot / video: `test-results/`

## CI 実行
- PR 向けのスモーク（`pull_request`）: `auth.spec.ts` / `guest.spec.ts` / `wordpack-list-states.spec.ts` / `wordpack.spec.ts` の主要導線と、一覧の空・該当なし・失敗・再読み込み状態を実行します。
- 手動回帰（`workflow_dispatch`）: Chromium で全シナリオを実行します。
- いずれの実行でも、画面表示後の axe a11y チェックを含めて品質を担保します。
- CI の成果物は GitHub Actions の該当ワークフロー実行ページ → Artifacts から取得できます。
  - `playwright-report/` と `test-results/` を保存し、保持期間は 90 日です。

## 性能系のE2E計測
- 主要導線の「操作 → 結果描画」までの所要時間を計測し、回帰がないかを確認します。
- 閾値は `E2E_ACTION_THRESHOLD_MS`（ミリ秒）で調整できます。既定値は 15000ms です。
- 計測結果は `[e2e-metric]` の JSON ログで出力され、CI のログ集計で可視化できます。

出力例:
```
[e2e-metric] {"event":"wordpack_generate_render_time","count":1,"average_ms":1234.56,"max_ms":1234.56,"measure_ms":1234.20,"threshold_ms":15000}
```

### 正例（閾値を緩めて計測）
```
E2E_ACTION_THRESHOLD_MS=20000 E2E_BASE_URL=http://127.0.0.1:5173 npm run e2e
```

### 負例（閾値が小さすぎてフレークになり得る）
```
E2E_ACTION_THRESHOLD_MS=200 E2E_BASE_URL=http://127.0.0.1:5173 npm run e2e
# → 環境差で 200ms を超えやすく、不要な失敗が増える
```

## 補足
- `tests/e2e/playwright.config.ts` に `baseURL` や `timeout`、成果物の出力先を集約しています。
- `BACKEND_PROXY_TARGET` は Vite のプロキシ先を固定するために `127.0.0.1:8000` を使用します。
