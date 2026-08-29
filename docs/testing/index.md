# テスト入口

この文書は、実行コマンドと変更pathからfocused / full gateを選ぶ入口です。テストの前提・判定基準・成果物の詳細は各リンク先、配送順序とgate証跡の失効は [GitHub配送Skill](../../.agents/skills/github-delivery/SKILL.md) を正本にします。

## ローカルでよく使うコマンド

| 種別 | コマンド | 詳細 |
|---|---|---|
| Backend full gate（coverage） | `PYTHONPATH=apps/backend pytest` | `pytest.ini` のcoverage付き全体検証。backendの入力閉包が最終HEADで変わる場合に選択 |
| Backend focused（no coverage） | `PYTHONPATH=apps/backend pytest -q --no-cov <test-or-node>` | coverage検証を目的としないfocused pytest。成功時のファイル別coverage明細を出さない |
| Security headers | `PYTHONPATH=apps/backend pytest -q --no-cov tests/test_security_headers.py` | セキュリティヘッダー検証 |
| Frontend typecheck | `cd apps/frontend && npx tsc -p tsconfig.json` | TypeScript 型検査 |
| Frontend tests | `cd apps/frontend && npm test -- --coverage --silent` | Vitest + coverage |
| Backend architecture boundaries | `PYTHONPATH=apps/backend pytest -q --no-cov tests/backend/test_architecture_boundaries.py` | Domain/Application の禁止 import と runtime 直呼び出しを検査 |
| Workflow / classifier contract | `PYTHONPATH=apps/backend pytest -q --no-cov tests/test_verification_inputs.py tests/test_github_actions_branch_policy.py tests/test_ui_test_change_classifier.py` | workflow条件、gate入力閉包、代表path分類のcontract test。focused pytestはcoverageなし |
| Workflow YAML parse | `python3 -c 'import pathlib,yaml; [yaml.safe_load(p.read_text(encoding="utf-8")) for p in pathlib.Path(".github/workflows").glob("*.y*ml")]'` | 変更workflowの構文を確認。意味上の条件はcontract testで確認 |
| Gate-input classification | `python3 scripts/classify_verification_inputs.py --base "$BASE_SHA" --head "$HEAD_SHA"` | gate入力閉包の `base...head` 差分を確認。判定不能時は広いgateへfallbackし理由を残す |
| UI-test classification | `python3 scripts/classify_ui_test_changes.py --base "$BASE_SHA" --head "$HEAD_SHA"` | UI test選択の `base...head` 差分を確認。判定不能時は安全側へfallbackする |
| Agent-harness full gate | `bash scripts/verify-agent-harness.sh` | agent-harnessだけの変更で選択。AI governance gateに含まれる場合は重複実行しない |
| AI governance full gate | `bash scripts/verify-ai-governance.sh` | UI governanceを含む最上位gate。内包するagent-harness gateは別途実行しない |
| LLMOps offline report | `python3 scripts/llmops/offline_report.py --json-output /tmp/llmops.json --markdown-output /tmp/llmops.md` | 外部 request 0件の fixture 契約検査。詳細は [LLMOps evaluation](../llmops/evaluation.md) |
| Frontend architecture boundaries | `node ./scripts/check_frontend_architecture_boundaries.mjs` | page / feature layer の API transport 直参照と legacy fetcher import を検査 |
| Backend p95 | `API_P95_THRESHOLD_MS=1500 PYTHONPATH=apps/backend pytest -q --no-cov tests/test_api_performance.py` | [backend-performance.md](./backend-performance.md) |
| Frontend integration | `cd apps/frontend && INTEGRATION_TEST=true BACKEND_PROXY_TARGET=http://127.0.0.1:8000 npm run test` | [frontend-integration-tests.md](./frontend-integration-tests.md) |
| Playwright smoke | `npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack-server-query.spec.ts tests/e2e/wordpack.spec.ts` | [playwright-e2e.md](./playwright-e2e.md) |
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

変更pathを分類し、影響する最小十分なfocused testを先に実行します。最終HEADでのfull gate選択と、同一入力閉包の証跡再利用・失効はGitHub配送Skillのledgerに記録します。

| 変更path / 影響 | focused test | 最終確認 |
|---|---|---|
| `.github/workflows/**`、`scripts/classify_ui_test_changes.py`、workflow/classifierのcontract test | contract test、変更workflowのYAML parse、`base...head` classification | latest Actions。backend application / Firestore / frontend runtimeに影響しない限りbackend full pytestや無関係なPlaywrightは選ばない |
| workflow未変更のreview fix（docs、classifier test、Skillなど） | 変更pathに対応するfocused test | 既存YAML証跡は保持し、変更workflowがないため再parseしない |
| `.agents/**`、`AGENTS.md`、`docs/agent-harness.md`、`docs/ai-governance/**`、`scripts/verify-*` | `git diff --check`、必要なfrontmatter / marker検査 | 変更範囲に応じてagent-harnessまたはAI governanceの最上位full gate |
| `apps/backend/backend/**`、Firestore/API設定・契約 | 対象pytestを `--no-cov` で実行。architecture / security境界は該当時に追加 | Firestore Emulator付きbackend full gate。frontend runtimeを変えない限りPlaywrightは不要 |
| `apps/frontend/src/**`、frontend設定・依存、hook / UI state | typecheckと対象Vitest | classifierに従うPlaywright smoke / visual、必要ならcoverage付きVitest |
| `tests/e2e/**`、主要導線、表示・レイアウト | 対象Playwrightまたは関連Vitest | 変更内容に対応するsmoke / visual。無関係なsuiteは選ばない |
| 文書・test-only（workflow/classifierを除く） | `git diff --check`、リンク・コマンド・公開安全性の目視 | 製品runtimeへ影響しない限りbackend full pytestやPlaywrightは不要 |

workflow/classifierの判定不能、diff取得失敗、未分類pathは、見逃しを避ける広い関連gateへfallbackし、原因を記録します。path分類だけで意味上の影響を確定できない場合も、skipを成功扱いにしません。

## Coverageと出力

`pytest.ini` の既定値はcoverage付きで、backend full gateの閾値確認に使います。coverage検証ではないfocused pytestは必ず `--no-cov` を付け、full gateと混同しません。coverage付きfull gateの成功報告は全体結果・閾値・artifact参照に絞り、file別coverage表や反復行はartifactへ残します。

## 成果物

- Playwright: `playwright-report/`, `test-results/`
- Vitest coverage: `apps/frontend/coverage/`
- pytest coverage: pytest 設定に従う

成果物は通常 Git へコミットしません。CI では GitHub Actions の artifacts から確認します。
