# UI/UXレビュー報告

## 1. 概要
<!-- agent-harness:uiux-report-scope:start -->

- 対象PR / 作業:
- 変更した画面・コンポーネント:
- review route: UI変更レビュー / フロー監査 / 併用
- 判定: Pass / Fail
- P0件数:
- P1件数:
- P2件数:

### 変更scope（UI変更レビューで差分がある場合）

| 項目 | 内容 |
|---|---|
| Target snapshot / ref |  |
| Base ref / SHA |  |
| Head ref / SHA |  |
| Commit / staged・unstaged diff |  |
| Diff identifier | `staged=<patch hash|empty>; unstaged=<patch hash|empty>; paths=<sorted changed path set>`。hash方式・取得時点も記録 |
| 追加側・削除側 |  |
| 変更意図（Issue / PR / commit） |  |
| Expanded surfaces | 直接consumer、parent、route、state、代表surface |
| Coverage / 未確認consumer / 除外理由 |  |
<!-- agent-harness:uiux-report-scope:end -->

## 2. ユーザー価値

- 対象ユーザー:
- 利用文脈:
- ユーザー目的:
- 支援するタスク:
- このUIが助ける理解・判断・行動:
- このUIがなければ困る点:
- 削るべき情報・操作:
- 検証仮説・成功指標:

## 3. 初見理解

- 何の画面か分かるか:
- 今どこか分かるか:
- 何ができるか分かるか:
- 最初の有意味な行動:
- 操作結果を予測できるか:
- 失敗時に戻れるか:

## 4. state matrix

`templates/state-matrix.md` を埋める。

## 5. アクセシビリティ確認

- キーボード:
- フォーカス:
- 名前・ラベル:
- 見出し・構造:
- コントラスト:
- ターゲットサイズ:
- エラー・ステータス:
- 自動検査:
- 手動確認:

## 6. 視覚階層

- 主操作:
- 情報優先度:
- グルーピング:
- 余白・密度:
- 読みやすさ:
- 狭幅・文字拡大:

## 7. コピー

- 用語:
- ボタン・リンク:
- エラー文:
- 空状態:
- disabled:
- トーン:

## 8. 熟練者効率

- 主要反復タスク:
- 手数:
- 再入力・再選択:
- 近道:
- 初心者向け説明の影響:
- 判定:

## 9. 満足感・信頼感

- 待機中:
- 成功時:
- 失敗時:
- 危険操作:
- データ・権限・個人情報:
- トーン:
- 判定:

## 10. 反証レビュー

- 実装を落とす観点で見つけた問題:
- P0候補:
- 証跡不足:
- 残リスク:

## 11. 指摘一覧
<!-- agent-harness:uiux-report-provenance:start -->

| 優先度 | Change status | Domain | 箇所 | 問題 | 影響 | 修正案 | 状態 |
|---|---|---|---|---|---|---|---|
| P0/P1/P2 | Introduced / Regression |  |  |  |  |  | 未対応/対応済 |

通常のPre-existingは今回の変更findingと完了判定へ混ぜず、変更起因件数・責任を次の欄へ分離します。

| Pre-existingの優先度 | 箇所 | 観測事実・証跡 | 今回の判定から分離する理由 | 完了判定への影響 | 別Issue / 後続 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

変更目的または安全性を阻害するP0/P1等のblocking findingは、Pre-existingであっても上部の判定と完了判定への影響欄に残し、別Issue化だけで完了扱いにしません。
<!-- agent-harness:uiux-report-provenance:end -->

## 12. 証跡

- スクリーンショット:
- トレース:
- テスト結果:
- 手動確認:
- 取得できなかった証跡と理由:

### フロー監査（発動時）

- 対象surface・ユーザー目的・監査対象タスク:
- 取得手段・開始状態・完了状態・重要な分岐:

| Step | 行動・到達状態 | screenshot参照またはblocker | 操作中に観測した挙動・確認手段 | 証跡上の限界 |
|---|---|---|---|---|
|  |  |  |  |  |

| Finding / P0・P1・P2 | Change status | Step / screenshot | 観測事実 | ユーザー影響 | 推奨対応 | 証跡上の限界 |
|---|---|---|---|---|---|---|
|  | Introduced / Regression / Pre-existing / N/A |  |  |  |  |  |

standaloneのフロー監査はdiff由来findingがないため、Change statusにN/A / 未分類（standalone）を記録してよく、Introduced / Regression / Pre-existingは必須ではありません。UI変更レビューまたは併用では、各findingのChange statusをIntroduced / Regression / Pre-existingのいずれかで記録します。Pre-existingの通常の変更起因件数・責任は上の分離欄へ記録しますが、変更目的または安全性を阻害するP0/P1等のblocking findingは上部の判定へ残し、scopeと完了判断を明示的に見直します。別Issue化だけで完了扱いにしません。

## 13. 実行した検証

- [ ] lint
- [ ] typecheck
- [ ] unit test
- [ ] integration / e2e
- [ ] accessibility check
- [ ] keyboard check
- [ ] responsive check
- [ ] visual regression
- [ ] その他:

## 14. 実行していない検証

| 未実行検証 | 理由 | 残リスク | 後続対応 |
|---|---|---|---|
|  |  |  |  |
