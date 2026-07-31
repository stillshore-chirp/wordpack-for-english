# UI/UXレビュー報告: Luna 単一モデル化

## 1. 概要

- 対象PR / 作業: Issue #563
- 変更した画面・コンポーネント: Lexicon の WordPack 作成欄、Reader の文章インポート欄、共通モデル設定
- 判定: Pass
- P0件数: 0
- P1件数: 0
- P2件数: 0

## 2. ユーザー価値

- 対象ユーザー: WordPack、Reader、Quiz の AI 生成を使うログイン済みユーザー
- 利用文脈: 新規生成、再生成、例文生成、記事化、Quiz 生成
- ユーザー目的: 性能条件を満たす Luna High を一貫して使用する
- 支援するタスク: モデルと生成詳細を確認して生成を開始する
- このUIが助ける理解・判断・行動: 現在使用されるモデルと推論量を生成前に確認できる
- このUIがなければ困る点: 将来モデルが増えた際に選択導線を再設計する必要があり、現在の実行設定も確認しにくい
- 削るべき情報・操作: 現時点ではなし。単一選択肢でも将来拡張のためモデル欄を維持することがユーザー要件
- 検証仮説・成功指標: Lexicon と Reader のモデル欄が Luna 1件、effort 既定が High で、旧保存値も新規リクエストでは Luna に正規化される

## 3. 初見理解

- 何の画面か分かるか: Lexicon / Reader の見出しと説明を維持
- 今どこか分かるか: 左ナビゲーションとモバイル下部ナビゲーションの選択状態を維持
- 何ができるか分かるか: モデル、`reasoning.effort`、`text.verbosity` のラベルを維持
- 最初の有意味な行動: 見出し語または文章を入力する既存導線を維持
- 操作結果を予測できるか: Luna と選択中パラメータで生成することを設定値から確認できる
- 失敗時に戻れるか: 既存のエラー表示、通知、再実行導線を変更していない

## 4. state matrix

| 状態 | 表示 | 操作 | 回復 | 判定 |
|---|---|---|---|---|
| 通常 | モデル `gpt-5.6-luna`、effort `high` | 対応する effort / verbosity を選択 | 再選択できる | Pass |
| 旧ローカル保存値 | UI では Luna へ正規化 | Luna で新規生成 | 自動移行 | Pass |
| 旧生成メタ情報 | 保存済みの旧モデル名を履歴表示 | 閲覧のみ | 書き換えない | Pass |
| 不正モデル / `minimal` | API が 422 相当の入力エラーとして拒否 | 対応値へ修正 | 許可値をエラーで確認 | Pass |
| ゲスト | Luna / High を表示し、AI 操作は無効 | 実行不可 | ログイン案内 | Pass |
| 狭幅 | モデルと詳細設定を縦方向に表示 | 既存のモバイル操作 | スクロール可能 | Pass |
| loading / empty / error | 既存状態を維持 | 既存の更新・再試行 | 既存導線 | Pass |

## 5. アクセシビリティ確認

- キーボード: ネイティブ `select` を維持し、選択肢追加による独自キーボード実装はない
- フォーカス: 既存フォーカス順と可視フォーカスを変更していない
- 名前・ラベル: `モデル`、`reasoning.effort`、`text.verbosity` の accessible name を Browser の DOM snapshot で確認
- 見出し・構造: Lexicon / Reader の見出し、main、navigation、region を維持
- コントラスト: 色・スタイル変更なし
- ターゲットサイズ: サイズ変更なし
- エラー・ステータス: ゲスト無効理由、空状態、生成キューを DOM snapshot で確認
- 自動検査: frontend typecheck、Vitest、Playwright smoke
- 手動確認: desktop 1280x720 と narrow 390x844

## 6. 視覚階層

- 主操作: 見出し語入力 / 文章入力と生成ボタンを既存位置に維持
- 情報優先度: 入力、生成操作、モデル詳細の順を維持
- グルーピング: モデル、effort、verbosity を同じ生成領域に維持
- 余白・密度: 選択肢内容のみ変更しレイアウト変更なし
- 読みやすさ: Luna 名が desktop / narrow の select 内で判読可能
- 狭幅・文字拡大: 390x844 で横方向にはみ出さず、モデル欄と詳細設定へ縦スクロールできる

## 7. コピー

- 用語: OpenAI 公式の model ID とパラメータ名を使用
- ボタン・リンク: 変更なし
- エラー文: 不正モデルと不正 effort は許可値を示す
- 空状態: 変更なし
- disabled: ゲスト時の理由表示を維持
- トーン: 技術設定は正確さを優先し、断定範囲を公式仕様に限定

## 8. 熟練者効率

- 主要反復タスク: WordPack / Reader / Quiz の連続生成
- 手数: 既定が Luna High のため、基準設定では追加選択不要
- 再入力・再選択: 旧モデル保存値は Luna へ自動正規化
- 近道: 既存キーボードショートカットと画面配置を維持
- 初心者向け説明の影響: 新しい常設説明は追加せず、UserManual に現在の単一モデル状態を記載
- 判定: Pass

## 9. 満足感・信頼感

- 待機中: 既存の生成キューと進行通知を維持
- 成功時: 既存の完了通知と生成メタ情報を維持
- 失敗時: 非対応値を暗黙変換せず API 境界で拒否
- 危険操作: 破壊的操作なし
- データ・権限・個人情報: 保存済み生成履歴を一括書き換えず、公開情報のみを証跡化
- トーン: 「使用中のモデル」と「過去の生成モデル」を混同しない
- 判定: Pass

## 10. 反証レビュー

- 実装を落とす観点で見つけた問題: 旧 `minimal` を型だけから除外しても任意 dict の API 入力から通る可能性があったため、全生成リクエスト境界へ validator を追加した
- P0候補: 旧環境変数が残りバックエンド起動または生成が失敗する可能性。env 例、ローカル env、既定値、設定文書を同時更新して解消
- 証跡不足: 実 OpenAI API への課金を伴う Luna 生成は未実行
- 残リスク: 本番 Cloud Run の既存 `LLM_MODEL` 実値はこのローカル変更では更新されない。デプロイ時の環境反映と実生成品質は運用確認が必要

## 11. 指摘一覧

| 優先度 | 箇所 | 問題 | 影響 | 修正案 | 状態 |
|---|---|---|---|---|---|
| P1 | API 入力 | 旧 `minimal` が任意 dict から送信可能 | Luna でリクエスト失敗 | 対応 effort を validator で制限 | 対応済 |
| P1 | 環境設定 | 旧モデル名が env 例と既定値に残る | 起動時または生成時の不整合 | Luna に統一 | 対応済 |
| P2 | UI | 単一選択肢でもモデル欄が残る | 一見すると冗長 | 将来拡張という明示要件に従い維持 | 対応済 |

## 12. 証跡

- 変更前: [Lexicon desktop](../evidence/issue-563/before-lexicon-desktop.jpg)、[Reader desktop](../evidence/issue-563/before-reader-desktop.jpg)
- 変更後: [Lexicon desktop](../evidence/issue-563/after-lexicon-desktop.jpg)、[Reader desktop](../evidence/issue-563/after-reader-desktop.jpg)、[Reader narrow](../evidence/issue-563/after-reader-narrow.jpg)
- テスト結果: backend 309 passed / 1 skipped、frontend 200 passed / 1 skipped、Playwright smoke 9 passed
- 手動確認: Luna 1選択肢、High 既定、6段階 effort、desktop / narrow、ゲスト無効理由、semantic labels
- 取得できなかった証跡と理由: 実 OpenAI API 生成は課金と外部状態変更を避け、mock Responses API の request-shape テストで代替

## 13. 実行した検証

- [x] typecheck
- [x] unit test
- [x] integration / e2e
- [x] accessibility check
- [x] keyboard check（ネイティブ select と既存フォーカス契約の自動テスト）
- [x] responsive check
- [x] visual regression（変更前後 screenshot）
- [x] AI governance verification

## 14. 実行していない検証

| 未実行検証 | 理由 | 残リスク | 後続対応 |
|---|---|---|---|
| 実 OpenAI API 生成 | 課金と外部 API 呼び出しを伴う | 実タスク品質、レイテンシ、総コストは未確認 | デプロイ後の限定スモークで確認 |
| 本番環境変数確認 | 本番調査依頼ではなくローカル実装 | 既存 `LLM_MODEL` override が残る可能性 | デプロイ時に Luna を明示し `/api/config` と生成メタ情報を確認 |
