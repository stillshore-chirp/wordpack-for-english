# Issue #550 UI/UX・アクセシビリティ・current-run evidence

## Scope と snapshot

- 対象: WordPack プレビューの例文コピー完了・失敗通知。
- 受入条件: 例文コピーで生成キュー／履歴を増やさないこと、上部の正確な成功文言、約5秒後の消去と連続操作時のタイマー再開、keyboard と status の name / role / live behavior、失敗時のグローバルな知覚、既存生成通知の維持。
- `before` は base commit `21dfbe355eec5d48d1ffc89fc1df826e95f2ace4` の clean temporary worktreeで取得した。現行 candidate は `HEAD` `595ccf4df9fbe6db08f176f9d872c5820624f883` に PR #627 の未コミット P2 修正を加えた状態である。
- base から現行 candidate までの実装対象5 pathの snapshot fingerprint は `e535fefba010cf187aec62835ab95f6f1e5644b15de4adecee24405d2f257091`、新規 `WordPackTransientMessage.tsx` の SHA-256 は `9ea7ebb65771aba9d164cc0075a88906e8dd8bd36d6b6534f6b1d288cb47b1d4`。現行未コミット P2 working diff（2 path）の fingerprint は `3c1543a916baa2b8f7e4e888d63ad7ded9590f76546642b8ca4d3de38916b9e5` である。
- 実装変更の対象は `UserManual.md`、`apps/frontend/src/WordPackPanel.test.tsx`、`apps/frontend/src/hooks/useExampleActions.ts`、`apps/frontend/src/features/wordpack/components/WordPackPanel/WordPackPanelContainer.tsx`、新規 `apps/frontend/src/features/wordpack/components/WordPackPanel/WordPackTransientMessage.tsx`。
- この lane の書込みは `docs/ai-governance/evidence/issue-550/` と本 report のみ。commit、push、実装 path の編集はしていない。

判定は **partial / unverified**。current snapshot の実装 blocker は確認していないが、実スクリーンリーダー、forced-colors、200% text resize、320 CSS px reflow はこの環境で実行していないため、アクセシビリティ全体の完了とは断定しない。

## UI/UX review findings

### 解消を確認した review finding

| Severity | Source classification | Finding と確認 | 状態 |
|---|---|---|---|
| P1 | Introduced | live region が message 発生時だけ mount されるリスク。現行は status と alert の二つの region を常時 DOM に置き、空状態も `visually-hidden` で accessibility tree に残し、`role`、accessible name、`aria-live`、`aria-atomic` を固定している（`WordPackTransientMessage.tsx:15-42`、`WordPackPanelContainer.tsx:621-622`）。 | source / DOM / regression test で解消を確認。実スクリーンリーダーの発話自体は未確認。 |
| P1 | Introduced | Clipboard の完了順、WordPack 切替、unmount 後の古い結果が現在の preview に表示されるリスク。operation id、WordPack/data context、mounted guard を現行実装で確認し、逆順完了の回帰 test が pass した（`useExampleActions.ts:401-458`、`WordPackPanel.test.tsx:546-636`）。 | 解消を確認。 |
| P2 | Regression (PR #627) | 同じ WordPack の mutable data（`ゲスト公開` 更新）で preview data reference が変わると、表示中のコピー通知が早期 clear されるリスク。transient-message context を WordPack identity のみに限定し、更新中も通知を保持して元の5秒で消去する回帰 test が pass した（`WordPackPanelContainer.tsx:133-169`、`WordPackPanel.test.tsx:425-488`）。 | 解消を確認。 |

### 現行 snapshot の所見

| Severity | Source classification | 観測事実・影響・推奨 |
|---|---|---|
| P2 | Pre-existing | 390 CSS px の after 画面では、既存の sticky `.wp-nav` が本文の例文ラベルへ重なり、狭幅で読み取りを阻害する。該当 CSS は `WordPackPanelContainer.tsx:605-607,633` にあり、base にも存在して今回の差分ではない。Issue #550 の変更起因には数えず、別途 responsive navigation の Issue 化を推奨する。 |
| P2 | Introduced follow-up risk | 失敗通知も共通の5秒 timer（`WordPackPanelContainer.tsx:148-162`）で消え、文言は `コピーに失敗しました`（`useExampleActions.ts:447-455`）のみである。assertive alert による即時通知と、画面に残るコピー操作による再試行は確認できるが、原因・回復案内を保持する設計ではない。今回の「グローバルに知覚可能」は満たす automated evidence があるため blocker とは判定しない。 |
| — | Evidence gap | 空の live region は `.is-empty visually-hidden`（`WordPackTransientMessage.tsx:15-30`、`WordPackPanelContainer.tsx:621-622`）で視覚的に隠しつつ DOM / accessibility tree に残る。表示切替時の VoiceOver/NVDA 発話、同一文言の再通知は実行していないため、支援技術での announcement evidence は未確認として残す。 |

PR #627 の targeted review では、現行 candidate に新規の P0 / P1 / P2 は報告されていない。上記の mutable data に関する P2 は、現行 candidate の回帰 test と source review により解消扱いとした。

## 実行した確認と結果

### Automated

- `npx tsc -p tsconfig.build.json --noEmit`（`apps/frontend`）: **PASS**。
- `npm test -- WordPackPanel.test.tsx hooks/__tests__/useExampleActions.test.ts --run`: **2 files、20 passed / 20**。Canvas API の既存 jsdom warning が stderr に出たが、失敗なし。
- `npm test -- --coverage --run`: 現行 candidate で **48 test files passed、1 skipped; 260 passed、1 skipped（261 total）**。全体 coverage は Stmts 87.41%、Branch 79.29%、Funcs 74.19%、Lines 87.41%。
- `git diff --check`: **PASS**。
- 回帰 test で、queue の `生成履歴 0件` がコピー前後で不変、成功文言、status の `role/name/aria-live`、5秒消去、連続コピーの timer reset、Clipboard rejection の alert、legacy fallback の focus restore と失敗、逆順 async completion、preview 切替後の stale result を確認した。
- 既存の生成通知経路は copy action から利用せず、生成・import 側の notification 契約を変更していないことを差分と全体 test で確認した。

### Current-run browser

決定論的な合成 fixture（見出し語 `theta` と合成例文）だけを使用し、production backend、実アカウント、実 job / request / trace identifier は使用していない。

- Desktop 1280×900: Lexicon から preview を開き、Dev 例文の Copy をクリック。画面上部に `✓例文をクリップボードにコピーしました` が表示され、`role=status`、name `例文コピー結果`、`aria-live=polite`、`aria-atomic=true`、alert は非表示。queue の accessible name は `生成履歴 0件` のまま。
- Keyboard: Copy button に focus した状態で Enter を送信。上記 status が表示され、focus は `thetaのDev例文1をコピー` に残った。queue は `生成履歴 0件`。
- Timer: 4.2秒後に再度 Copy、そこから3秒時点では status が表示中、さらに2.3秒後（再操作から約5.3秒）に status が消えた。連続操作による timer reset を確認。
- Mobile 390×844 CSS viewport: Dev 例文へ scroll して Copy を実行。成功文言は2行へ折り返され、body/modal の scrollWidth は 375、clientWidth も 375 で横 overflow はない。status rect は 296×75.6 CSS px。
- Focus / contrast: Desktop の copy button は 54.2×26.2 CSS px、active 時に青い outline / box-shadow が見える。dark theme の status は `#e5e7eb` on `#111827`（計算値 14.33:1）、accent `#60a5fa` on `#111827`（6.98:1）、focus `#1976d2` on `#111827`（3.85:1）。status の font は 16px / 24px、pointer-events は none。
- `prefers-reduced-motion: reduce` は browser capability で true を確認し、通知に animation / transition がないことを確認。`forced-colors: active` は false の環境だったため未確認。final candidate の空 region は `display:flex` のまま `clip-path: inset(50%)`、1×1 CSS px へ visually-hidden 化され、success 表示時のレイアウトには影響しないことを DOM / screenshot で確認した。
- Clipboard failure の実ブラウザ注入は実行していない。browser の page evaluation は read-only であり、失敗を作るために page API を改変しなかった。failure は rejection と `execCommand('copy')` false を使う regression test で `role=alert`、name `例文コピーエラー`、`aria-live=assertive`、`コピーに失敗しました`、queue 0 を確認した。
- PR #627 の current diff は transient message の CSS と `WordPackTransientMessage` の markup を変更せず、preview identity 比較と回帰 test のみを更新していることを source / diff で確認した。したがって、以下の after 画像は表示内容について現行 candidateへ再利用可能と判断し、画像自体は再取得・変更していない。

## 画面証跡の provenance

取得時刻は Asia/Tokyo、画像は接続済み browser の `fullPage: false` screenshot API で取得した JPEG である。取得後に dimensions、形式、表示内容を確認した。`after` 画像は PR #627 の P2 修正前に取得した visual candidate由来だが、現行 candidateの P2 diff は可視 CSS / component markup を変更していないことを source / diff で確認したため、その表示証跡を再利用している。

| 画像 | snapshot | 取得時刻 | CSS viewport / raster | 操作と観測 |
|---|---|---|---|---|
| [before: base preview](../evidence/issue-550/lexicon-copy-before.jpg) | clean base `21dfbe3…` | 2026-08-29 18:34:36 +09:00 | 1280×900 / 1280×900 | preview を開いた直後。copy transient message なし、既存 queue は0件。 |
| [after: desktop success](../evidence/issue-550/lexicon-copy-after-final.jpg) | pre-PR #627 P2 visual candidate; current candidate reuse validated (`e535fef…`, component `9ea7ebb…`) | 2026-08-29 19:08:30 +09:00 | 1280×900 / 1280×900 | Dev 例文を Copy、250ms 後に撮影。上部 success message、queue 0件。 |
| [after: mobile success](../evidence/issue-550/lexicon-copy-after-mobile.jpg) | pre-PR #627 P2 visual candidate; current candidate reuse validated (`e535fef…`, component `9ea7ebb…`) | 2026-08-29 19:09:55 +09:00 | 390×844 / 375×812 | モーダル内を Dev 例文まで scroll、Copy、250ms 後に撮影。2行表示、横 overflow なし。 |

base と after は同一の決定論的 fixture で比較した。画像には実ユーザーの本文、認証情報、production log、実識別子を含めていない。過去 commit `881c9d21213aa42e201a053c950508ed789f0560` や過去画像は今回の証跡として使用していない。

## 未確認範囲と残るリスク

- VoiceOver / NVDA 等の実スクリーンリーダーで、空の visually-hidden region から成功・失敗文言へ更新した際の発話、同一文言の再通知、modal 内の reading order は未確認。final candidate では安定 region と announcement key の source / test を確認済み。
- forced-colors / Windows High Contrast、200% text resize、320 CSS px reflow、OS の text spacing は未確認。今回の mobile smoke は390 CSS pxであり、これらの代替にはならない。
- Clipboard の permission denial や browser-specific legacy API の実環境挙動は automated fallback test の範囲に留まる。
- 390 CSS px の sticky navigation overlap は Pre-existing の P2。Issue #550 の transient message 自体は表示・折り返しできるが、本文の可読性リスクは残る。
- 固定 fixture は copy UI、queue 不変、通知 semantics を検証するが、production backend の認可、Firestore、実ユーザーの履歴状態は検証しない。

## Base → current candidate の fingerprint / Git diff --stat

```text
 UserManual.md                                      |   1 +
 apps/frontend/src/WordPackPanel.test.tsx           | 304 ++++++++++++++++++++-
 .../WordPackPanel/WordPackPanelContainer.tsx       |  71 +++++
 .../WordPackPanel/WordPackTransientMessage.tsx     |  45 +++
 apps/frontend/src/hooks/useExampleActions.ts       |  66 +++++-
 5 files changed, 477 insertions(+), 10 deletions(-)
```

上記は base `21dfbe3…` から現行 working treeまでの実装対象5 pathの stat である。現行未コミット PR #627 working diff（2 path）は次のとおりである。

```text
 apps/frontend/src/WordPackPanel.test.tsx           | 65 ++++++++++++++++++++++
 .../WordPackPanel/WordPackPanelContainer.tsx       |  6 +-
 2 files changed, 67 insertions(+), 4 deletions(-)
```

evidence JPEG と本 report は上記の product-path stat には含めていない。最終的な履歴回収・commit・push は親 agent の責務であり、この lane では実行していない。
