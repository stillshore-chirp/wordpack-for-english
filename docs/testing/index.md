# テスト入口

この文書はテスト種別ごとの入口です。詳細な前提や成果物は各リンク先を正本にします。

## ローカルでよく使うコマンド

| 種別 | コマンド | 詳細 |
|---|---|---|
| Backend | `PYTHONPATH=apps/backend pytest` | backend 全体の pytest |
| Security headers | `PYTHONPATH=apps/backend pytest -q --no-cov tests/test_security_headers.py` | セキュリティヘッダー検証 |
| Frontend typecheck | `cd apps/frontend && npx tsc -p tsconfig.json` | TypeScript 型検査 |
| Frontend tests | `cd apps/frontend && npm test -- --coverage --silent` | Vitest + coverage |
| Backend architecture boundaries | `PYTHONPATH=apps/backend pytest -q --no-cov tests/backend/test_architecture_boundaries.py` | Domain/Application の禁止 import と runtime 直呼び出しを検査 |
| Frontend architecture boundaries | `node ./scripts/check_frontend_architecture_boundaries.mjs` | page / feature layer の API transport 直参照と legacy fetcher import を検査 |
| Backend p95 | `API_P95_THRESHOLD_MS=1500 PYTHONPATH=apps/backend pytest -q --no-cov tests/test_api_performance.py` | [backend-performance.md](./backend-performance.md) |
| Frontend integration | `cd apps/frontend && INTEGRATION_TEST=true BACKEND_PROXY_TARGET=http://127.0.0.1:8000 npm run test` | [frontend-integration-tests.md](./frontend-integration-tests.md) |
| Playwright smoke | `npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack-list-states.spec.ts tests/e2e/wordpack.spec.ts` | [playwright-e2e.md](./playwright-e2e.md) |
| Visual regression | `E2E_BASE_URL=http://127.0.0.1:5173 npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/visual.spec.ts` | [visual-regression.md](./visual-regression.md) |

Firestore Emulator を使う Backend CI は Java 21 を前提とし、Python 3.13 と 3.14 の両方で同じ pytest suite を実行します。さらに `Dockerfile.backend` を Python 3.14 でビルドし、コンテナの `/healthz` まで確認します。ローカルで同じ suite を実行する場合は、Java 21 と Firebase CLI を用意したうえで次を使います。

```bash
FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 \
FIRESTORE_PROJECT_ID=wordpack-ci \
GCP_PROJECT_ID=wordpack-ci \
PYTHONPATH=apps/backend \
firebase emulators:exec --only firestore --project wordpack-ci --config firebase.json "python -m pytest"
```

## 種別ごとの正本

- Backend performance: [docs/testing/backend-performance.md](./backend-performance.md)
- Vitest coverage: [docs/testing/vitest-coverage.md](./vitest-coverage.md)
- Frontend integration: [docs/testing/frontend-integration-tests.md](./frontend-integration-tests.md)
- Playwright E2E: [docs/testing/playwright-e2e.md](./playwright-e2e.md)
- Visual regression: [docs/testing/visual-regression.md](./visual-regression.md)

## 実行判断

- backend のロジック、API、設定、Firestore 境界を変える場合は backend pytest を優先します。
- Domain / Application / frontend feature 境界を変える場合は architecture boundary check を含めます。
- セキュリティヘッダー、CORS、host、proxy、session まわりを変える場合は security headers test を含めます。
- frontend の TypeScript / React / hook / UI state を変える場合は typecheck と Vitest を実行します。
- 主要導線やユーザー操作が変わる場合は Playwright smoke を検討します。
- 見た目、レイアウト、余白、レスポンシブ挙動が変わる場合は visual regression を検討します。
- 文書のみの変更では `git diff --check` とリンク/コマンド/公開安全性の目視確認を最低限実施します。

## 成果物

- Playwright: `playwright-report/`, `test-results/`
- Vitest coverage: `apps/frontend/coverage/`
- pytest coverage: pytest 設定に従う

成果物は通常 Git へコミットしません。CI では GitHub Actions の artifacts から確認します。
