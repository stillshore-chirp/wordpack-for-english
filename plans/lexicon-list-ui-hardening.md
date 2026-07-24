# Lexicon List UI Hardening Plan

## Goal

Lexicon の一覧を、右レール、狭幅、文字拡大、長い見出し語、大量データ、空・該当なし・失敗状態でも、対象と次の操作を誤認せずに使える UI へ改善する。

## Done When

- Issue #544 の表示崩壊、視覚順とフォーカス順の不一致、操作過密が解消されている。
- Issue #545 の初回空、該当なし、読み込み失敗が区別され、回復導線がある。
- Issue #164 の適用中検索語・検索方式・絞り込み条件が確認・解除できる。
- Issue #115 の検索・絞り込みがページング全体へ適用され、件数が一貫する。
- 各 Issue を独立した非ドラフト PR で順次対応し、最新 head の CI と未解決 review thread を確認する。
- 各 UI 変更で安全なモックデータによる変更前/変更後スクリーンショット、state matrix、初見、a11y、視覚階層、熟練者効率、信頼感、反証レビューを残す。
- README / UserManual / docs / `.gitignore` / AGENTS の更新要否を各 slice で確認する。

## Priority Slices

- [x] Audit: 添付画像、実画面、DOM、実寸レイアウト、現行コード、既存テストを確認する。
- [x] Issue inventory: P0/P1 を独立 Issue に分け、既存 Issue と重複照合する。
- [x] P0 #544: リスト表示を単列・安全な操作階層へ変更し、表示崩壊とフォーカス順を直す。
- [ ] P0 #545: 初回空、該当なし、読み込み失敗を区別し、回復導線を追加する。
- [ ] P1 #164: 適用中の検索・絞り込み条件を表示・解除できるようにする。
- [ ] P1 #115: ページング全体へ検索・絞り込みと集計を適用する。
- [ ] Completion: 全 slice の CI、Codex 自動レビュー、review thread、残リスクを確認する。

## Resume Command

```bash
cd /private/tmp/wordpack-list-ui-20260724
git status --short --branch
sed -n '1,240p' plans/lexicon-list-ui-hardening.md
cat plans/lexicon-list-ui-hardening.status.json
```

## Smoke Tests

```bash
cd apps/frontend && npx tsc -p tsconfig.json
cd apps/frontend && npm test -- WordPackListPanel.actions-layout.test.tsx WordPackListPanel.modal.test.tsx
npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/wordpack.spec.ts
```

## Session Notes

- 2026-07-24: 公開中の Lexicon で、CSS viewport 1636×912、右レール表示、リスト2列時に主領域約963pxへ約1234pxの一覧グリッドがはみ出し、先頭項目の見出し語領域が0pxになることを確認した。
- 2026-07-24: Issue #544 と #545 を新規作成し、既存 Issue #164 と #115 の本文を現在の受け入れ条件へ更新した。
- 2026-07-24: Issue #544 の単列リスト、操作メニュー、キーボード移動、変更前後の安全なモック証跡、長文・右レール・390px幅の回帰検証を実装した。PR / CI / review 確認を継続する。
- 2026-07-24: Issue #544 の初回 CI は全 check 成功。Codex 自動レビューで補助操作の可視ラベルと公開先の曖昧さを検出したため、カード・リスト双方へ「その他」を表示し、「ゲスト公開にする / ゲスト公開を解除」へ具体化した。
- 2026-07-24: レビュー反映 head `9155921` の全 CI が成功し、Codex review thread 2件へ回答して解決済みにした。PR #546 は非ドラフトのまま merge 待ち。
