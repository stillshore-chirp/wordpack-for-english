# Clean Architecture completion plan

## Goal

Issue #522 の範囲として、既存 API / Firestore schema / 認証・ゲスト閲覧 / 主要 UI 挙動を維持しながら、Clean Architecture 境界をコード、テスト、CI、ドキュメントで確認できる状態にする。

## Non-goals

- REST API path や response shape の意図的な変更。
- Firestore collection/schema の破壊的変更。
- UI の画面文言、導線、レイアウトの意図的な再設計。
- OpenAI / Cloud Run / Firebase の実運用設定値の公開。

## External behavior invariants

- `/api/word/pack`, `/api/word/packs`, `/api/word/packs/{id}`, `/api/word/examples`, `/api/article/import`, `/api/article/generate_and_import`, `/api/quiz`, `/api/quiz/generate/jobs`, `/api/tts` を維持する。
- request / response shape と documented status を維持する。
- `guest_public` による WordPack / Example / Reader / Quiz のゲスト閲覧制御を維持する。
- custom event `auth:unauthorized`, `wordpack:updated`, `wordpack:study-progress`, `article:updated` を維持する。

## Architecture target

- Domain / Application は FastAPI、Firestore、OpenAI SDK、HTTP request/response、global store、router monkeypatch、frontend 都合を知らない。
- LLM / TTS / Firestore / job scheduling / clock / ID 生成 / settings は外側 adapter から注入する。
- Router は HTTP validation、auth dependency、application service 呼び出し、HTTP error mapping を担当する。
- frontend page は API transport を直接持たず、feature infrastructure adapter を経由する。
- legacy path は互換 shim として残す場合でも、新規内部コードから import しない。

## Completion checklist

- [x] Issue-first: #522 を作成。
- [x] backend architecture boundary test を追加。
- [x] frontend architecture boundary script を追加。
- [x] CI に frontend architecture boundary check を追加。
- [x] WordPack flow orchestration を infrastructure adapter へ移し、application import path を compatibility export に限定。
- [x] empty WordPack の LLM sense title 生成を infrastructure adapter へ移動。
- [x] WordPack guest-public use case から FastAPI Request / HTTPException / datetime 依存を排除。
- [x] WordPack regeneration job use case から direct store import / HTTPException / uuid / direct task scheduling を排除。
- [x] Quiz generation job use case から flow / uuid / datetime / direct task scheduling を排除。
- [x] frontend feature API adapter が shared API transport を使うよう更新。
- [x] test backend app reload helper を monkeypatch 管理にし、全体 pytest の module state 汚染を解消。
- [x] full backend pytest。
- [x] security headers pytest。
- [x] frontend typecheck / Vitest / build。
- [x] Playwright smoke。
- [x] docs update verification。
- [ ] PR / CI / Codex review gate。

## Slices

1. Boundary harness and plan.
2. Backend application dependency cleanup.
3. Frontend boundary cleanup.
4. Docs and verification updates.
5. PR publication and CI/review follow-up.

## Verification commands

```bash
git diff --check
PYTHONPATH=apps/backend pytest
PYTHONPATH=apps/backend pytest -q --no-cov tests/test_security_headers.py
cd apps/frontend && npx tsc -p tsconfig.json
cd apps/frontend && npm test -- --coverage --silent
node ./scripts/check_frontend_architecture_boundaries.mjs
npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack.spec.ts
```

## Resume commands

```bash
cd /Users/Taishi/.codex/worktrees/2551/wordpack-for-english
git status --short --branch
sed -n '1,220p' plans/clean-architecture-completion.md
cat plans/clean-architecture-completion.status.json
```

## Risks and mitigations

- Legacy import paths still exist for compatibility. Mitigation: backend AST test and frontend script prevent new internal boundary violations in the explicit clean layers.
- Existing legacy components under `src/components` still act as compatibility UI surfaces. Mitigation: feature/page boundaries are enforced now; future UI decomposition can move those components under `features/*/presentation` without changing behavior.
- Production job execution remains in-process scheduling with persistent job records. Mitigation: application no longer owns task scheduling, and job status is read from persistent store when available.

## Current progress

- Work branch: `codex/complete-clean-architecture`
- Issue: #522
- Local targeted verification passed for backend architecture, WordPack regeneration jobs, Quiz generation jobs, router compatibility, and Quiz API.
- Full backend pytest passed after fixing `_reload_backend_app` module isolation.
- Security headers pytest passed.
- Frontend TypeScript, Vitest coverage, production build, and frontend architecture boundary script passed.
- Playwright smoke passed for auth / guest / WordPack critical flows.
