# アーキテクチャ概要

この文書は、backend/frontend の責務配置を把握するための内部構造メモである。
API path、Firestore collection/document schema、認証・ゲスト閲覧の契約は `docs/api-reference.md`、`docs/firestore.md`、`docs/authentication.md`、`docs/guest_public_api.md` と各 API テストを正とし、
ここでは実装上の依存方向だけを扱う。

## Backend

FastAPI の起動構造は `backend.main` から `backend.app` 配下へ分離している。
`backend.main:app` と `backend.main:create_app` は互換 entrypoint として維持し、
実際の app 生成、middleware、router 登録、startup/shutdown は次の責務に分ける。

| モジュール | 責務 |
| --- | --- |
| `backend.app.factory` | `FastAPI` インスタンス生成と構成の接続点 |
| `backend.app.middleware_stack` | CORS、proxy、host、security、rate limit、access log の登録 |
| `backend.app.routers` | API router の include と debug router の環境制御 |
| `backend.app.lifecycle` | startup seed と provider cleanup |
| `backend.observability.*` | Cloud Trace header 解析、access log/metrics、Langfuse tracing |

設定は `backend.settings.base.Settings` に実体を置き、`backend.config` は互換 facade として残す。
既存テストや外部呼び出しが `from backend.config import settings` を使っても同じ `settings` オブジェクトを参照する。

Firestore は既存の `AppFirestoreStore` を互換 facade として残しつつ、
`backend.infrastructure.firestore.repositories` に concrete repository、
`backend.domain.*` に typed record/repository protocol を置く。
新しい usecase は repository 境界へ寄せ、既存 router やテストで必要な `backend.store.store` は compatibility shim として維持する。

Domain / Application 境界は `tests/backend/test_architecture_boundaries.py` で AST 検査する。
`backend.domain.*` は FastAPI、Firestore、OpenAI、HTTP client、settings/store/router/presentation/infrastructure を import しない。
`backend.application.*` は FastAPI、Firestore、OpenAI、settings/store/router/presentation/infrastructure を import せず、`asyncio.create_task`、`uuid.uuid4`、`datetime.now` を直接呼ばない。
旧 import path を維持するための compatibility export は allowlist に限定し、新規内部コードは infrastructure adapter や shared API を直接参照する。

WordPack の API router は `backend.routers.word` package に分割し、route 定義と dependency/error mapping に寄せる。
`backend.routers.word.__init__` は互換 entrypoint として `router`、`store`、`run_wordpack_flow`、`generate_word_pack_id`、`_regenerate_jobs` を公開する。
各 route module の責務は次の通り。

| モジュール | 責務 |
| --- | --- |
| `backend.routers.word.lookup_routes` | `GET /api/word` の lemma lookup、guest 公開判定 |
| `backend.routers.word.pack_routes` | WordPack 作成、一覧、詳細、削除 |
| `backend.routers.word.generation_routes` | WordPack 生成 API と LLM flow 呼び出し |
| `backend.routers.word.regeneration_routes` | 同期/非同期 regeneration と job status |
| `backend.routers.word.example_routes` | 例文生成、一覧、一括削除、文字起こし入力 |
| `backend.routers.word.study_progress_routes` | WordPack / example の学習進捗 |
| `backend.routers.word.guest_public_routes` | WordPack 単位の guest public 更新 |
| `backend.routers.word.lemma_routes` | `GET /api/word/lemma/{lemma}` |
| `backend.routers.word.dependencies` | legacy monkeypatch を壊さない store / flow / ID 依存解決 |
| `backend.routers.word.error_mapping` | LLM / empty content の HTTP error mapping |

生成、lookup、空 WordPack 作成、学習進捗、guest public、再生成 job registry は `backend.application.wordpack` に置く。
ただし OpenAI provider、`WordPackFlow` orchestration、空 WordPack の LLM sense title 生成は `backend.infrastructure.llm` の adapter が担当する。
WordPack regeneration job は application が repository、flow runner、task scheduler、ID generator を port として受け取り、`asyncio.create_task` と uuid 生成は `backend.infrastructure.runtime` へ隔離する。
LLM prompt と JSON parser は `backend.infrastructure.llm` に置き、code fence 除去と control character sanitize を共通化する。

Quiz は WordPack とは別 feature として、`backend.models.quiz`、`backend.routers.quiz`、`backend.application.quiz.*`、`backend.domain.quiz.prompt_policy`、`backend.infrastructure.llm.quiz_generator`、`backend.infrastructure.firestore.repositories.quizzes` に分離する。`format_profile` は出題構造、`generation_domain` は題材、`domain_intensity` は専門性の強さを制御し、特定試験名や公式問題の再現を UI/DB/prompt の主要カテゴリにしない。Firestore では `quizzes`、`quiz_word_packs`、`quiz_attempts` を使い、`AppFirestoreStore` facade から保存・一覧・詳細・削除・Attempt 保存を公開する。
Quiz generation job も application が generator、task scheduler、ID generator、clock を port として受け取り、Flow 実行は `QuizGenerateFlowAdapter` が担う。

Article import の lemma filtering は `backend.domain.article.lemma_filter` に集約する。
function word/basic lemma の除外、多語句の保持、重複排除はこの domain 関数を通す。

Firestore helper は `backend.infrastructure.firestore.batch` / `search_terms` / `mappers` / `payloads` に切り出す。
`backend.infrastructure.firestore.repositories.*` は Firestore concrete repository の実体を持ち、users / wordpacks / examples / articles / app_store の責務に分割する。
`backend.store.firestore_store` は既存テストが直接 monkeypatch する `_now_iso` や `FirestoreWordPackStore` を残すため compatibility facade として維持し、旧 class 名は infrastructure repository の subclass または alias として公開する。
旧 `backend.infrastructure.firestore.wordpack_repository` などは re-export とする。

## Frontend

`src/App.tsx` は互換 entrypoint として `src/app/App.tsx` を re-export する。
`src/app/App.tsx` は `ThemeApplier`、`AuthGate`、`AppShell` の composition だけを担当する。
実際の app shell、theme 適用、auth telemetry、WordPack feature は次の責務に分ける。

| モジュール | 責務 |
| --- | --- |
| `src/app/AppShell.tsx` | route state、sidebar state、focus restore、main content composition |
| `src/app/AuthGate.tsx` | 認証済み/guest と login screen の切り替え |
| `src/app/Header.tsx` / `Sidebar.tsx` / `BottomNav.tsx` | 共通 layout の presentational UI |
| `src/app/LoginScreen.tsx` / `GoogleLoginCard.tsx` | login / guest entry と Google OAuth UI |
| `src/app/keyboardShortcuts.ts` | Esc、Alt+数字、`/` focus の keyboard shortcut |
| `src/app/navigation.ts` | nav item と shell 定数 |
| `src/app/styles/*` | app shell / login CSS。旧 inline CSS から移動 |
| `src/app/routes.ts` | `/lexicon`、`/wordpacks/:id`、`/reader`、`/examples`、`/explore`、`/shelves`、`/quiz`、`/settings` の軽量 route 互換 |
| `src/pages/*Page` | Lexicon / WordPack Detail / Reader / Examples / Explore / Shelves / Quiz / Settings の画面単位の構成 |
| `src/pages/ExplorePage` | 既存WordPack詳細を読み取り、関連語・共起・対比・例文の接続カードへ変換する Connection Explorer |
| `src/pages/ShelvesPage` | 既存WordPack一覧を条件別に自動分類する Smart Shelves |
| `src/pages/QuizPage` | Quiz 生成フォーム、保存済みQuiz一覧、本文読解、採点、解説、本文中 WordPack 操作をまとめる学習画面 |
| `src/features/auth` | Google OAuth telemetry と sanitization |
| `src/features/wordpack` | WordPack domain types、API helper、feature hooks/components。旧 `src/components/WordPackPanel.tsx` は re-export |
| `src/features/quiz` | Quiz domain types、API helper、表示ラベル。QuizPage はここから API/type を利用する |
| `src/features/article-import` | Article import API/type/hook/components。旧 `src/components/ArticleImportPanel.tsx` は re-export |
| `src/shared/api` | `ApiError`、JSON fetch、FastAPI detail parse、401 event dispatch |
| `src/shared/events` | `auth:unauthorized`、`wordpack:updated`、`wordpack:study-progress`、`article:updated` の typed event helper |
| `src/shared/ui` / `src/shared/styles` | 辞書UI向けの共通コンポーネント、theme token、layout utility |
| `src/lib/fetcher.ts` | 既存 import path 用の compatibility re-export |

`auth:unauthorized`、`wordpack:updated`、`wordpack:study-progress`、`article:updated` の custom event は公開契約として扱う。
旧 import path は compatibility shim として残し、feature 配下への直接 import を新規コードの標準とする。
`scripts/check_frontend_architecture_boundaries.mjs` は `src/pages/**` が API transport を直接使わないこと、feature の domain/application/presentation 層がそれぞれ React / presentation / transport を持ち込まないこと、feature code が `src/lib/fetcher.ts` ではなく `src/shared/api` を使うことを検査する。
新しい画面は既存 API と既存 panel の責務を壊さず、外側の AppShell / page 構成で辞書探索型の情報設計へ寄せる。

## Compatibility shims

次の path は互換 shim として残す。

| Legacy path | 実体 |
| --- | --- |
| `backend.main:app` / `backend.main:create_app` | `backend.app.factory` |
| `backend.config` | `backend.settings` |
| `backend.application.wordpack.generate_wordpack` | `backend.infrastructure.llm.wordpack_generator` |
| `backend.routers.word` | `backend.routers.word.*` package |
| `backend.store.firestore_store.AppFirestoreStore` | Firestore compatibility facade over infrastructure repositories |
| `backend.models.word._validate_lemma` | `backend.domain.wordpack.lemma.validate_lemma` |
| `apps/frontend/src/App.tsx` | `src/app/App.tsx` |
| `src/components/WordPackPanel.tsx` | `src/features/wordpack/components/WordPackPanel` |
| `src/components/ArticleImportPanel.tsx` | `src/features/article-import/components/ArticleImportPanel` |
| `src/lib/fetcher.ts` | `src/shared/api/*` |
