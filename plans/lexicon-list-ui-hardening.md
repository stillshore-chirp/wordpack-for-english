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
- [x] P0 #545: 初回空、該当なし、読み込み失敗を区別し、回復導線を追加する。
- [x] P1 #164: 適用中の検索・絞り込み条件を表示・解除できるようにする。
- [x] P1 #115: ページング全体へ検索・絞り込みと集計を適用する。
- [ ] Completion: 全 slice の CI、Codex 自動レビュー、review thread、残リスクを確認する。

## Resume Command

```bash
cd /private/tmp/wordpack-list-server-query-20260724
git status --short --branch
sed -n '1,240p' plans/lexicon-list-ui-hardening.md
cat plans/lexicon-list-ui-hardening.status.json
```

## Smoke Tests

```bash
(cd apps/frontend && npx tsc -p tsconfig.json)
(cd apps/frontend && npm test -- --silent src/WordPackListPanel.states.test.tsx)
PYTHONPATH=apps/backend pytest -q --no-cov tests/backend/test_wordpack_list_query.py
PYTHONPATH=apps/backend pytest -q --no-cov tests/test_api.py -k 'word_pack_list'
npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/wordpack-active-conditions.spec.ts tests/e2e/wordpack-list-states.spec.ts tests/e2e/wordpack-server-query.spec.ts
```

## Session Notes

- 2026-07-24: 公開中の Lexicon で、CSS viewport 1636×912、右レール表示、リスト2列時に主領域約963pxへ約1234pxの一覧グリッドがはみ出し、先頭項目の見出し語領域が0pxになることを確認した。
- 2026-07-24: Issue #544 と #545 を新規作成し、既存 Issue #164 と #115 の本文を現在の受け入れ条件へ更新した。
- 2026-07-24: Issue #544 の単列リスト、操作メニュー、キーボード移動、変更前後の安全なモック証跡、長文・右レール・390px幅の回帰検証を実装した。PR / CI / review 確認を継続する。
- 2026-07-24: Issue #544 の初回 CI は全 check 成功。Codex 自動レビューで補助操作の可視ラベルと公開先の曖昧さを検出したため、カード・リスト双方へ「その他」を表示し、「ゲスト公開にする / ゲスト公開を解除」へ具体化した。
- 2026-07-24: レビュー反映 head `9155921` の全 CI が成功し、Codex review thread 2件へ回答して解決済みにした。PR #546 は非ドラフトのまま merge 待ち。
- 2026-07-24: PR #546 の最終 head `365e1ef` から Issue #545 の依存ブランチを作成し、初回読み込み中、初回空、検索・絞り込み0件、初回失敗、更新中、更新失敗を分離した。前回一覧保持、回復操作、live region、狭幅を unit / Playwright / axe と固定モック証跡で検証済み。#546 merge 後に main へ載せ替えて PR / CI / review gate を進める。
- 2026-07-24: Issue #164 の依存ブランチで、検索方式付きの適用中条件、個別・全解除、解除後フォーカス、セッション復元時の上部検索同期、全体/このページ/条件一致件数を追加した。frontend 197件、PR相当Playwright 16件、axe、390px、固定モック変更前後をローカル確認済み。先行PR群の merge 後に main へ順次載せ替えて PR / CI / review gate を進める。
- 2026-07-24: Issue #115 の依存ブランチで、認可範囲全体への検索・公開/生成状態絞り込み・安定ソートをAPIへ移し、全体件数、全ページ一致件数、切替候補件数を分離した。条件切替中は旧件数を確定表示しない。backend 310件（1件skip）、frontend 198件（1件skip）、PR相当Playwright 18件、visual 6件、typecheck、architecture boundaries、axe、390px、固定モック変更前後を検証済み。先行PR群の merge 後に順次公開する。
