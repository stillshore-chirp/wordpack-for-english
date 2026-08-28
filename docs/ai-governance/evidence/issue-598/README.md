# Issue #598 UI evidence

Quiz の英日文対応検証、生成進捗、失敗理由、生成日時表示を、公開用の合成データとモック API を使った Playwright E2E で確認した証跡です。利用者提供の本文、画像、実ジョブ ID、実トレース ID は含みません。

## 確認画面

- `quiz-detail-three-columns.png`: 詳細画面の3カラム表示と生成日時
- `quiz-detail-focus.png`: 全体表示モードでも維持される生成日時と英日本文
- `quiz-detail-mobile-200-percent.png`: 390px幅・200%文字拡大時の到達性
- `quiz-generation-retry-progress.png`: 文対応の再確認段階と試行回数
- `quiz-generation-alignment-failure.png`: 5回失敗時の理由と回復案内

修正前の事象画像は利用者提供本文を含むため公開しません。代替証跡として、Issue本文に匿名化した再現条件とコード上の原因を記録し、共通fixtureの回帰testで段落内文数不一致を固定しています。残るリスクは、決定論的検証が文数の一致を保証する一方、翻訳の意味的正しさまでは評価しない点です。
