# UI/UXレビュー報告: Quiz生成フォームのWordPack候補制御

## 1. 概要

- 対象PR / 作業: Issue #511 Quiz作成で生成済みWordPackだけを選択し任意lemma自動セットを追加する
- 変更した画面・コンポーネント: `apps/frontend/src/pages/QuizPage`
- 判定: Pass
- P0件数: 0
- P1件数: 0
- P2件数: 0

## 2. ユーザー価値

- 対象ユーザー: 保存済みWordPackから長文読解Quizを作る学習者・編集者
- 利用文脈: Quiz生成前に、題材に含める語を選ぶ
- ユーザー目的: 実際に内容が生成済みのWordPackを使って、読解Quizの題材を素早く指定する
- 支援するタスク: 生成済み候補の選択、任意lemmaの自動入力、Quiz生成前の入力確認
- このUIが助ける理解・判断・行動: 未生成WordPackを誤って含める判断を避け、後続ページを含む生成済み候補から3件を素早く使える
- このUIがなければ困る点: 空WordPackを選べてしまい、Quiz生成の題材として使えるかをユーザーが判断し直す必要がある
- 削るべき情報・操作: 未生成候補は選択肢から削除した。自動入力ボタンは1つに絞り、主操作の生成開始とは視覚的に分けた
- 検証仮説・成功指標: 未生成WordPackをQuiz sourceへ入れる誤選択が減り、任意lemma入力の手数が減る。計測は未実施

## 3. 初見理解

- 何の画面か分かるか: Quiz生成フォーム。ページ見出しとフォーム見出しで判断できる
- 今どこか分かるか: サイドバーのQuiz選択状態とページ見出しで判断できる
- 何ができるか分かるか: 出題条件、含めるWordPack、任意lemmaを指定してQuiz生成できる
- 最初の有意味な行動: 出題条件を確認し、含めるWordPackまたは任意lemmaを指定する
- 操作結果を予測できるか: 「お任せで3件セット」は任意lemmaへ3件を入れる動作として読める
- 失敗時に戻れるか: 入力欄は通常のtextareaで、上書き後も編集・削除できる

## 4. state matrix

| 状態 | ユーザーが見るもの | 次にできる行動 | 判定 |
|---|---|---|---|
| 通常 | 生成済みWordPackだけの複数選択、任意lemma、自動セットボタン | 候補選択、ボタンで任意lemma入力、手入力 | Pass |
| 読み込み中 | 既存のQuiz一覧読み込み表示。WordPack候補は取得後に表示 | 待機、または任意lemmaを手入力 | Pass |
| 空 | WordPack候補が0件ならselectは空、自動セットボタンは無効 | 任意lemmaを手入力 | Pass |
| 検索結果なし | この画面に検索はない | N/A | Pass |
| 部分データ | 一覧取得済みの生成済み候補だけを表示 | 表示候補または任意lemmaを使う | Pass |
| エラー | WordPack一覧取得失敗は既存通りconsole warningで、Quiz生成は任意lemmaで継続可能 | 任意lemmaで続行 | Pass |
| 入力エラー | WordPack/lemmaがどちらも空なら入力エラー文を表示 | 候補選択またはlemma入力 | Pass |
| 無効 | 自動セット候補が0件ならボタン無効、理由をhelperで表示 | 任意lemmaを手入力 | Pass |
| 権限不足 | ゲストは既存GuestLockにより生成開始不可 | 閲覧・ローカル採点 | Pass |
| オフライン/利用不可 | 明示的なoffline検知はなし | 既存通信エラー経路に従う | Pass |
| 狭幅 | ラベルとボタンはflex-wrapで折り返す | 同じ操作を継続 | Pass |
| 文字拡大 | ボタンとhelperは折り返し、textareaは縦に伸びる | 同じ操作を継続 | Pass |
| 長文・大量データ | WordPack一覧を全ページ取得し、生成済みだけを表示 | 複数選択または自動セット | Pass |

## 5. アクセシビリティ確認

- キーボード: select、textarea、buttonはいずれもネイティブ要素。Tabで到達し、Enter/Spaceでボタン実行できる
- フォーカス: 既存focus-visibleルールがボタン・入力へ適用される
- 名前・ラベル: `含めるWordPack`、`任意 lemma`、`お任せで3件セット`が表示ラベルとaccessible nameになる
- 見出し・構造: 既存フォーム構造を維持
- コントラスト: 既存のsecondary button/helper配色を使用
- ターゲットサイズ: secondary buttonは既存の最小高さを継承
- エラー・ステータス: 自動セット成功は`role=status`の既存メッセージ領域で通知
- 自動検査: Vitest/Testing Libraryによるrole/label検証を実施
- 手動確認: Playwrightでdesktop/mobile viewportの表示と操作を確認

## 6. 視覚階層

- 主操作: Quiz生成開始はprimary buttonのまま維持
- 情報優先度: 自動セットは任意lemma欄の補助操作として同じグループ内に配置
- グルーピング: WordPack候補、候補説明、任意lemma補助を近接配置
- 余白・密度: 既存フォーム密度に合わせ、追加説明はhelper 2行相当へ抑制
- 読みやすさ: 未生成除外件数と自動セット件数を短い文で表示
- 狭幅・文字拡大: mobile viewportでボタンとtextareaが重ならないことを確認

## 7. コピー

- 用語: ユーザー指定の「含めるWordPack」「任意 lemma」を使用
- ボタン・リンク: 「お任せで3件セット」で結果を示す
- エラー文: 既存の必須入力エラーを「含めるWordPackまたはlemma」に揃えた
- 空状態: 自動セット候補がない場合は、生成済みWordPackが必要と示す
- disabled: helperで無効理由を表示
- トーン: ユーザーを責めず、表示条件と次の行動を事実として示す

## 8. 熟練者効率

- 主要反復タスク: Quiz生成前のsource指定
- 手数: 任意lemmaを3件手入力する手数を1クリックへ短縮
- 再入力・再選択: ボタンはtextareaを上書きするが、そのまま編集できる
- 近道: 生成済み候補から先頭3件を自動入力
- 初心者向け説明の影響: helperは短く、主操作を押し下げすぎない
- 判定: Pass

## 9. 満足感・信頼感

- 待機中: WordPack候補読み込みは既存挙動を維持
- 成功時: 自動セット後に何件セットしたかをstatusで表示
- 失敗時: 候補がない時はボタン無効とhelperで理由を表示
- 危険操作: 破壊的操作なし
- データ・権限・個人情報: 個人情報や権限変更なし
- トーン: 不安を煽らず、候補から除外した件数だけを表示
- 判定: Pass

## 10. 反証レビュー

- 実装を落とす観点で見つけた問題: 未生成候補が送信stateに残る可能性を考慮し、候補再読込時に`selectedWordPackIds`を生成済みIDへ同期した。自動レビューで、先頭100件に未生成が偏ると後続ページの生成済み候補を取りこぼす問題が指摘されたため、WordPack一覧を全ページ取得する実装と回帰テストを追加した
- P0候補: なし
- 証跡不足: 実ユーザーテストとmobile実機確認は未実施
- 残リスク: 自動セットの候補順はAPI一覧順に依存する

## 11. 指摘一覧

| 優先度 | 箇所 | 問題 | 影響 | 修正案 | 状態 |
|---|---|---|---|---|---|
| P0/P1/P2 | N/A | なし | N/A | N/A | 対応不要 |

## 12. 証跡

- スクリーンショット: `/private/tmp/wordpack-quiz-before.png`, `/private/tmp/wordpack-quiz-after.png`, `/private/tmp/wordpack-quiz-after-mobile.png`
- トレース: N/A
- テスト結果: `npm test -- src/pages/QuizPage/QuizPage.test.tsx --silent`（7 tests）, `npx tsc -p tsconfig.json`, `npm test -- --coverage --silent`
- 手動確認: Playwrightで変更前は`fallback`が候補に表示され、変更後は候補から消え、`お任せで3件セット`で`mitigate, latency, reliable`が入力されることを確認。mobile viewportではボタンとtextareaのbounding boxが重ならないことを確認
- 取得できなかった証跡と理由: 実ユーザーテストは実施していない。production実データは今回のUI実装範囲外

## 13. 実行した検証

- [ ] lint: 未実行（専用lint scriptなし）
- [x] typecheck: `npx tsc -p tsconfig.json`
- [x] unit test: `npm test -- src/pages/QuizPage/QuizPage.test.tsx --silent`
- [x] integration / e2e: Playwright手動ブラウザ確認
- [x] accessibility check: Testing Library role/label確認、キーボード可能なネイティブ要素を確認
- [x] keyboard check: ネイティブselect/textarea/button構造とfocus-visible適用を確認
- [x] responsive check: Playwright mobile viewport screenshotで確認
- [x] visual regression: スクリーンショットを取得
- [x] その他: `npm test -- --coverage --silent`

## 14. 実行していない検証

| 未実行検証 | 理由 | 残リスク | 後続対応 |
|---|---|---|---|
| Backend full pytest | API契約・backend実装を変更していない | backend既存回帰の検出範囲はCIに依存 | CIで確認 |
| Playwright smoke full suite | 対象変更はQuiz生成フォームで、既存必須smokeはauth/guest/wordpack中心 | 横断導線の視覚差分は限定的 | CIまたは必要時に実行 |
| 実ユーザーテスト | 実装タスク内で参加者検証は未実施 | 自動セット候補順の好みは未検証 | 利用ログやフィードバックで見直す |
