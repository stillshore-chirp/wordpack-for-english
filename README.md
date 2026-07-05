# WordPack for English

自由探索型の個人用英語辞書です。WordPack の生成・保存・例文・読解・クイズ・音声再生を、FastAPI backend と React + Vite frontend のモノレポで提供します。

| Lexicon | Reader | Examples |
|---|---|---|
| <img width="600" alt="スクリーンショット 2026-06-08 1 41 55" src="https://github.com/user-attachments/assets/dd2f606d-1215-4b20-b033-d73dd4b04704" /> | <img width="600" alt="スクリーンショット 2026-06-08 1 43 49" src="https://github.com/user-attachments/assets/3d903357-8e1d-455d-b2d1-01ef8e7a29c0" /> | <img width="600" alt="スクリーンショット 2026-06-08 1 44 37" src="https://github.com/user-attachments/assets/55fa5da7-7353-4268-b744-d452ffd918b7" /> |
| <img width="600" alt="スクリーンショット 2026-06-08 1 42 16" src="https://github.com/user-attachments/assets/26b983e1-92c2-493b-a8a3-716aa474e969" /> | <img width="600" alt="スクリーンショット 2026-06-08 1 44 16" src="https://github.com/user-attachments/assets/27835a40-ac97-4a1b-8b3e-f607c27320d9" /> | <img width="600" alt="スクリーンショット 2026-06-08 1 45 11" src="https://github.com/user-attachments/assets/1060e107-6ade-4485-8636-5228711022e6" /> |
| <img width="600" alt="スクリーンショット 2026-06-08 1 42 47" src="https://github.com/user-attachments/assets/4c96b995-3c7e-4910-8f92-e8b6e55c50d8" /> |  |  |

## 主な機能

- Lexicon / Reader / Examples / Explore / Shelves / Quiz / Settings を横断する辞書型 UI
- WordPack の生成、再生成、保存、公開設定、学習記録、例文管理
- 保存済み WordPack を使った関連語探索、Smart Shelves、長文読解 Quiz
- Google ログインとゲスト閲覧モード。ゲストは公開済み WordPack / Example / Reader / Quiz を読み取り専用で閲覧
- OpenAI LLM による語義・例文・記事化と、gpt-4o-mini-tts による音声再生
- Firestore を使った WordPack / 例文 / 記事 / Quiz の永続化
- Cloud Run + Firebase Hosting を想定した本番デプロイと GitHub Actions CI/CD

## クイックスタート

### 前提

- Python 3.13
- Node.js 20.19.0+
- Firestore エミュレータを使う場合は Java 21+

### セットアップ

```bash
cp env.example .env
# .env で SESSION_SECRET_KEY を32文字以上にし、生成機能を使う場合は OPENAI_API_KEY も設定します。

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

npm install
npm run prepare:frontend-env

cd apps/frontend
npm install
```

`.env` の詳しい意味、Google OAuth、Firestore、Cloud Run などの設定は [docs/環境変数の意味.md](docs/環境変数の意味.md)、[docs/authentication.md](docs/authentication.md)、[docs/firestore.md](docs/firestore.md)、[docs/deployment.md](docs/deployment.md) を参照してください。

### 起動

```bash
# Backend
python -m uvicorn backend.main:app --reload --app-dir apps/backend

# Frontend
cd apps/frontend
npm run dev
```

ブラウザで `http://127.0.0.1:5173` を開きます。Docker Compose でまとめて起動したい場合は `docker compose up --build` を使えます。

## ドキュメント

| 読みたいこと | 文書 |
|---|---|
| 画面の使い方、ゲスト閲覧、主要操作 | [UserManual.md](UserManual.md) |
| 文書の住み分けと README の責務 | [docs/documentation-structure.md](docs/documentation-structure.md) |
| backend/frontend の責務配置 | [docs/architecture.md](docs/architecture.md) |
| インフラ構成、CI/CD の全体像 | [docs/infrastructure.md](docs/infrastructure.md) |
| AI 処理フロー | [docs/flows.md](docs/flows.md) |
| OpenAI モデル設定 | [docs/models.md](docs/models.md) |
| 環境変数 | [docs/環境変数の意味.md](docs/環境変数の意味.md) |
| Google OAuth / セッション / ゲスト認証 | [docs/authentication.md](docs/authentication.md) |
| Firestore インデックス、エミュレータ、シード | [docs/firestore.md](docs/firestore.md) |
| Cloud Run / Firebase Hosting / GitHub Actions デプロイ | [docs/deployment.md](docs/deployment.md) |
| REST API 一覧 | [docs/api-reference.md](docs/api-reference.md) |
| ゲスト公開 API の詳細 | [docs/guest_public_api.md](docs/guest_public_api.md) |
| テスト種別と実行入口 | [docs/testing/index.md](docs/testing/index.md) |
| 本番監視、SLO、障害復旧 | [OPERATIONS.md](OPERATIONS.md) |
| AI エージェント作業ルール | [AGENTS.md](AGENTS.md) |
| AI エージェント支援開発の品質管理 | [docs/ai-governance/00-index.md](docs/ai-governance/00-index.md) |

### AI支援開発の運用ルールについて

`docs/ai-governance/` は、企業全体のAI統制や法務・倫理審査、モデル監査を指すものではなく、このリポジトリ内でAIエージェントを使って開発する際の作業ルール、UI/UXレビュー観点、検証証跡、完了条件を整理した開発運用ドキュメントです。

AIに実装を丸投げするのではなく、作業範囲、品質基準、確認結果、未実行項目、残リスクを明示し、レビュー可能な形で開発を進めるための補助線として整備しています。

## 主要ディレクトリ

```text
apps/backend/backend/   FastAPI backend
apps/frontend/          React + TypeScript + Vite frontend
tests/                  Python tests
tests/e2e/              Playwright E2E / visual tests
docs/                   開発・運用・仕様ドキュメント
docs/testing/           テスト種別ごとの詳細
.agents/                AI エージェント用スキル
.github/workflows/      CI/CD workflows
```

## 開発メモ

- デフォルトブランチは `main` です。PR と CI の運用は [AGENTS.md](AGENTS.md) と [docs/documentation-structure.md](docs/documentation-structure.md) を参照してください。
- README は初見訪問者向けの入口です。詳細仕様や運用手順は `docs/` 側を正本にします。
