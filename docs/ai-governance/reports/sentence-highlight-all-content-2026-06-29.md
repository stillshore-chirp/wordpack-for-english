# UI/UXレビュー報告: 文単位ハイライトのコンテンツ横断適用

## 1. 概要

- 対象PR / 作業: Quiz限定だった文単位ハイライトを Reader / Example / WordPack 例文へ適用し、1文だけのコンテンツでは無効化
- 変更した画面・コンポーネント: QuizPage、ArticleDetailModal、ExampleDetailModal、WordPack ExamplesSection
- 判定: Pass
- P0件数: 0
- P1件数: 0
- P2件数: 1

## 2. ユーザー価値

- 対象ユーザー: 英文と日本語訳を対応させながら読む学習者、Reader / Example / WordPack / Quiz を横断して復習する利用者
- 利用文脈: 本文や例文を読みながら、訳文のどの文に対応するかを短時間で確認したい場面
- ユーザー目的: 英文と訳文の対応を見失わず、文ごとに理解を確認する
- 支援するタスク: 2文以上あるコンテンツでの対応文探索、訳文確認、文単位の読解復習
- このUIが助ける理解・判断・行動: hover / focus で対応文を一時確認し、click / Enter / Space で確認中の対応を固定できる。1文だけの場合は全文強調で視認性を落とさないよう操作対象にしない
- このUIがなければ困る点: Reader や例文では長めの英文と訳文を目で追って対応を探す必要があり、Quizだけ操作感が異なる
- 削るべき情報・操作: 新しい説明テキストやボタンは追加せず、既存本文上の文単位操作に限定した
- 検証仮説・成功指標: 対象コンテンツで、対応する英文・訳文が同じ active / pinned 状態になる

## 3. 初見理解

- 何の画面か分かるか: 既存の Reader / Example / WordPack / Quiz 見出しを維持
- 今どこか分かるか: 既存ナビゲーション、モーダルタイトル、セクション見出しを維持
- 何ができるか分かるか: 文に hover / focus すると同時強調され、クリックで固定される。Quizと同じ操作に揃えた
- 最初の有意味な行動: 読んでいる英文または訳文へポインタを合わせる、またはTabで対応文へ移動する
- 操作結果を予測できるか: activeは一時確認、pinnedは固定確認として色を分けた
- 失敗時に戻れるか: 同じ文を再クリックすると固定解除でき、別文クリックで固定対象を切り替えられる

## 4. state matrix

| 状態 | 観察内容 | 判定 |
|---|---|---|
| 通常 | Quiz / Reader / Example / WordPack で英文と訳文が既存レイアウト内に表示される | Pass |
| hover | 対応する英文・訳文が `is-active` になる | Pass |
| click / keyboard | 対応する英文・訳文が `is-pinned` になる | Pass |
| 解除 | 同じ文の再クリックで固定解除できる | Pass |
| 読み込み中 | 本文表示前の既存ローディング状態を変更しない | Pass |
| 空 | 既存の空状態を変更しない | Pass |
| 検索結果なし | Example / WordPack の既存検索・絞り込み状態を変更しない | Pass |
| 部分データ | 訳文がない場合はペア操作を有効化しない | Pass |
| 1文のみ | 対応する文ペアが1つだけのコンテンツでは `is-paired` とfocusableな `role=group` を付けず、全文だけが光る状態を避ける | Pass |
| エラー | 既存エラー表示を変更しない | Pass |
| 入力エラー | 既存フォーム入力エラーを変更しない | Pass |
| 無効 | 既存 disabled 操作を変更しない | Pass |
| 権限不足 | ゲスト制限・GuestLock を変更しない | Pass |
| オフラインまたは利用不可 | 既存通信エラー表示を変更しない | Pass |
| 狭幅 | 既存の折り返しと段落表示を維持し、文spanはinlineで折り返す | Pass |
| 文字拡大 | 文spanは本文行内で折り返し、固定サイズを持たない | Pass |
| 長文・大量データ | Reader長文でも段落と文単位に分割される。大量文ではTab停止数が増える | P2 |

## 5. アクセシビリティ確認

- キーボード: Reader / Example 詳細 / Quiz は2文以上の文spanを `role="group"` + `tabIndex=0` にし、Enter / Space で固定可能。WordPack例文は英文ブロックの既存語句操作を維持するため、訳文側から固定可能。1文だけのコンテンツでは不要なTab停止を作らない
- フォーカス: `.sentence-pair-highlight:focus-visible` を共通定義し、Quiz固有の `.quiz-sentence:focus-visible` も維持
- 名前・ラベル: `英文 N: 日本語訳と対応`、`日本語訳 N: 英文と対応` を accessible name として付与
- 見出し・構造: 既存の見出し、list、region、modal構造を維持
- コントラスト: activeはaccent、pinnedはgreenで色と背景/枠の組み合わせを使い、色だけに依存しない
- ターゲットサイズ: 文spanは本文そのものを対象にし、既存ボタンのtarget sizeを変更しない
- エラー・ステータス: 新規エラー状態なし。既存エラー表示を変更しない
- 自動検査: Vitest coverage、Playwright smokeを実行
- 手動確認: 差分レビューでclick無視対象、InlineWordPack操作、GuestLock操作との衝突がないことを確認

## 6. 視覚階層

- 主操作: 本文読解が主目的のため、新しいボタンや説明カードは追加しない。1文だけの本文では全文強調を出さず、読みやすさを優先
- 情報優先度: 文の強調はユーザーが注目した文だけに限定
- グルーピング: 同じpairKeyの英文・訳文だけを active / pinned にする
- 余白・密度: 既存の段落間隔、例文カード密度、Quiz本文密度を維持
- 読みやすさ: `white-space: pre-wrap` と `overflow-wrap` を維持し、長文折り返しを壊さない
- 狭幅・文字拡大: inline spanのため追加横スクロールを作らない

## 7. コピー

- 用語: 既存の「英文」「日本語訳」「原文」「訳文」を維持
- ボタン・リンク: 新規ボタンなし
- エラー文: 新規エラーなし
- 空状態: 既存空状態を変更しない
- disabled: 新規disabledなし
- トーン: 学習者を責める文言や過剰な注意文を追加しない

## 8. 熟練者効率

- 主要反復タスク: 文を読みながら訳文対応を確認する
- 手数: 追加ボタンを押さず、hover / focus / click だけで確認できる
- 再入力・再選択: なし
- 近道: クリックで固定、再クリックで解除
- 初心者向け説明の影響: 常時表示の説明を増やしていない
- 判定: Pass

## 9. 満足感・信頼感

- 待機中: 既存ローディングを維持
- 成功時: active / pinned の即時フィードバックで操作結果が分かる
- 失敗時: 新規通信や保存を行わないためデータ損失なし
- 危険操作: なし
- データ・権限・個人情報: 本文表示上のローカルUI操作のみ。権限や公開状態は変更しない
- トーン: 追加コピーなし
- 判定: Pass

## 10. 反証レビュー

- 実装を落とす観点で見つけた問題: WordPack例文の英文ブロックは既に関連WordPackを開く操作対象で、文spanをfocusableにするとネストした操作対象になるため、英文側はhoverのみ、訳文側はkeyboard/click対応にした
- P0候補: InlineWordPackボタンをクリックしたときに文固定が誤発火する問題は、click無視対象で防いだ
- Codex reviewで見つけた問題: Reader / Exampleのコンテンツ切替時に同じpairKeyの固定状態が持ち越される可能性と、Reader本文の単一改行が再構成で失われる可能性を修正した
- 利用後に見つけた問題: 1文だけのコンテンツでは全文が強調されるだけで対応探索の価値がなく、むしろ読みにくくなるため、対応文ペアが2つ以上ある場合だけ有効化した
- 証跡不足: 専用スクリーンショットは未取得。DOMテストとPlaywright実ブラウザ操作で主要状態を確認した
- 残リスク: Reader長文では文ごとのTab停止数が増える。長大記事向けのroving focusやショートカットは別Issue候補

## 11. 指摘一覧

| 優先度 | 箇所 | 問題 | 影響 | 修正案 | 状態 |
|---|---|---|---|---|---|
| P2 | Reader長文 | 文ごとにTab停止するため、非常に長い記事ではキーボード移動回数が増える | 熟練者が長文で本文後続操作へ移動する手数が増える | 長文Reader向けに文ペア領域のroving focusまたはショートカットを検討 | 未対応 |

## 12. 証跡

- スクリーンショット: 未取得
- トレース: Playwright smoke 9 passed
- テスト結果:
  - `cd apps/frontend && npx tsc -p tsconfig.json`: pass
  - `cd apps/frontend && npm test -- --run src/components/ArticleDetailModal.test.tsx src/components/ExampleDetailModal.test.tsx src/components/wordpack/ExamplesSection.test.tsx src/pages/QuizPage/QuizPage.test.tsx --silent`: 32 passed
  - `cd apps/frontend && npm test -- --coverage --silent`: 188 passed / 1 skipped
  - `npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack.spec.ts`: 9 passed
  - `git diff --check`: pass
  - 公開文書の秘密情報・運用IDキーワードスキャン: no matches
- 手動確認: 差分レビューでQuizの既存ARIA名、Reader/Example/WordPackの適用、1文だけのコンテンツでは `is-paired` / focusable group が付かないこと、UserManual更新、公開文書の秘密情報なしを確認
- 取得できなかった証跡と理由: スクリーンショットは未取得。今回の検証では状態クラスとARIA名を自動テストで確認し、Playwright smokeで実ブラウザ操作を確認した

## 13. 実行した検証

- [ ] lint
- [x] typecheck
- [x] unit test
- [x] integration / e2e
- [x] accessibility check
- [x] keyboard check
- [x] responsive check
- [ ] visual regression
- [x] その他: `git diff --check`

## 14. 実行していない検証

| 未実行検証 | 理由 | 残リスク | 後続対応 |
|---|---|---|---|
| lint | リポジトリ必須コマンドではなく、typecheck / Vitest coverage / Playwright smokeを優先 | lint固有の規約違反はCI待ち | CIで失敗したら修正 |
| visual regression | 既存baselineがなく、今回は状態クラスと実ブラウザ操作を優先 | 微細な見た目差分 | 必要ならReader/Example/WordPackのスクリーンショットテストを追加 |
| backend pytest | フロントエンド表示と文書更新のみで、backend契約やAPI挙動を変更していない | backend全体の未確認 | CIで確認 |
