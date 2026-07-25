# Shelves UI/UX 監査と是正

## 目標

Shelves で棚を選び、保存済み WordPack を探してプレビューする主要導線を、初見・キーボード・狭幅・失敗状態でも理解して完了できる状態にする。

## 対象 Issue

- #553: 「開く」で選択棚の WordPack 一覧へ移動し結果を通知する
- #551: 棚検索と WordPack 絞り込みの結果・件数・空状態を一致させる
- #552: 読み込み・空・取得失敗・部分データを区別して回復可能にする
- #554: 操作名・選択状態・件数コピー・検索ショートカットを整合させる

## 完了条件

- P0 指摘がすべて解消される。
- 通常、読み込み中、空、検索結果なし、部分データ、エラー、更新中、狭幅、文字拡大、長文・大量データの state matrix が記録される。
- 棚の「開く」で対象一覧が画面内に入り、見出しへフォーカスし、支援技術へ選択結果が伝わる。
- 検索の棚カード、選択棚、一覧、件数、右レール、空状態が同じ対象を示す。
- 一意な accessible name、可視フォーカス、キーボード操作、axe の確認を通す。
- 全件分類または部分データの明示により、200件超で分類範囲を誤認させない。
- UserManual と UI/UX レビュー報告が現状仕様に一致する。
- 変更前後スクリーンショットを PR 本文へ添付する。
- ローカル検証、最新 head の CI、CI 後の review thread 確認が完了する。

## 優先度付き小タスク

1. P0: 「開く」の移動・フォーカス・通知を実装する。
2. P0: 検索結果と選択・件数・空状態を同じ状態モデルへ統合する。
3. P0: loading / empty / error / stale-data / partial-data を分離し、再試行可能にする。
4. P0/P1: 操作名、選択状態、件数コピー、内部用語、検索ショートカットを整合させる。
5. Unit / Playwright / axe / キーボード / 狭幅 / 文字拡大の回帰証跡を追加する。
6. UserManual、UI/UX レビュー報告、PR 前後画像を更新する。
7. commit、push、非ドラフト PR、CI、Codex レビュー、review thread を完了する。

## 再開コマンド

```bash
git switch codex/shelves-uiux-audit
git status --short --branch
sed -n '1,200p' plans/shelves-uiux-audit.status.json
```

## 基本スモークテスト

```bash
cd apps/frontend
npm test -- --run src/pages/ShelvesPage/ShelvesPage.test.tsx
npx tsc -p tsconfig.json
cd ../..
npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/shelves.spec.ts
```

## 変更対象外

- Shelves 以外の画面の情報設計変更
- Smart Shelf の新しい分類ルール追加
- ユーザー定義棚、ドラッグ並べ替え、一括操作
