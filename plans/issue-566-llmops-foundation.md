# Issue #566 LLMOps 基盤整備計画

## 目標

通常の PR、push、main merge、production deploy の使用感と外部 LLM 呼び出し数を変えず、Git 管理の prompt identity、privacy-safe な generation provenance、無料の offline evaluation、完全手動の live evaluation を利用できるようにする。

## 完了条件

- Issue #566 の受け入れ条件を、コード、fixture、テスト、workflow、文書で第三者が検証できる。
- legacy `complete()` / `complete_text()`、既存 test double、既存保存 write 回数を維持する。
- 通常 CI と deploy が live evaluation や LLMOps 用 secret を参照せず、外部 LLM request が 0 件であることを静的検査とテストで固定する。
- 変更を commit / push し、非 draft PR の最新 head で CI 成功、Codex review thread 対応完了を確認する。

## 優先度付き小タスク

- [x] P0: 全 LLM call site、prompt builder、Responses API、Langfuse span、Firestore 保存経路、CI/deploy trigger を棚卸しする。
- [x] P0: 現行 call count / write count と legacy provider 互換性を回帰テストで固定する。
- [x] P0: prompt identity、typed completion result、compact provenance、`store=False`、requested/effective fallback 観測を実装する。
- [x] P0: raw prompt/output を production 既定で送らず、Langfuse/metadata serialization の失敗を非致命にする。
- [x] P1: WordPack と 5 category examples の offline fixture/evaluator/report を追加する。
- [x] P1: `workflow_dispatch` 限定、estimate-only 既定、confirm と hard limit 付き live evaluation を追加する。
- [x] P1: backend CI summary と静的 guard を追加し、LLMOps secret / live evaluator 非参照を固定する。
- [x] P1: `docs/llmops/` を正本として README、models、flows、OPERATIONS、testing から入口を追加する。
- [x] P0: backend、architecture boundary、frontend、Playwright smoke、governance、公開安全性を検証する。
- [ ] P0: PR、CI、reviewThreads を完了ゲートまで追跡する。

## 再開コマンド

```bash
cd /Users/Taishi/Documents/GitHub/wordpack-for-english
git switch codex/issue-566-llmops-foundation
git status --short
sed -n '1,240p' plans/issue-566-llmops-foundation.md
PYTHONPATH=apps/backend pytest -q tests/test_providers.py tests/llmops tests/test_llmops_ci_policy.py
```

## 基本スモークテスト

```bash
PYTHONPATH=apps/backend pytest
cd apps/frontend && npx tsc -p tsconfig.json && npm test -- --coverage --silent
cd ../.. && npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack.spec.ts
bash scripts/verify-ai-governance.sh
git diff --check
```

## 進捗ログ

- 2026-08-01: Issue 本文と最新 `main` を確認し、専用ブランチを作成。現行 provider が prompt preview と raw output を Langfuse / 構造化ログへ送る経路、`store=False` 未指定、string-only provider contract を持つことを確認した。
- 2026-08-01: typed completion、compact provenance、offline/live evaluation、CI policy、運用文書を実装。call count、write count、並行分離、privacy、非致命性を回帰テストで固定した。
- 2026-08-01: backend、frontend、Playwright、Cloud Run dry-run、governance をローカル検証。live evaluation の実リクエストは費用回避のため未実行とした。

## 残るリスク

- live evaluation の実リクエストは費用を発生させるため、この変更作業では実行せず、estimate、guard、fake client で検証する。
- production の Langfuse / Cloud Logging / Firestore 実データは本番調査依頼ではないため確認対象外とし、設定とテストで契約を検証する。
