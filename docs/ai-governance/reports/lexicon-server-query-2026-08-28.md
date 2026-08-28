# UI/UXレビュー報告: Lexicon全ページ検索・件数整合 2026-08-28

## 対象と目的

- 対象Issue: #115
- 対象画面: Lexicon の保存済みWordPack一覧
- 対象ユーザー: 201件以上のWordPackを保存し、検索・公開状態・生成状態で対象を探す利用者
- 目的: 条件を認可範囲全体へ適用し、後続ページだけにある一致項目を欠落させず、件数の対象範囲を判別できるようにする

## 変更した状態と情報

- 検索、公開状態、生成状態、並び順をAPIへ送り、条件適用後にページ分割する。
- 条件変更時は先頭ページへ戻し、件数変動でページが範囲外になった場合は最後の有効ページへ補正する。
- `全体`、`条件一致（全ページ）`、`このページ` を分離する。
- 公開・生成状態の候補件数は、他の条件を保った全ページ集計として表示する。
- 条件取得中は前回一覧を保持して件数を確定表示せず、失敗時は前回一覧、未取得表示、再試行を提供する。

## State matrix

| 状態 | 表示 | 次の行動 | 証跡 |
|---|---|---|---|
| 通常 | 全体・条件一致・このページ件数と一覧 | 閲覧、条件変更、ページ移動 | component test / E2E |
| 201件目だけ一致 | 先頭ページに一致項目1件 | 項目を開く、条件変更 | backend境界値test / E2E |
| 条件変更中 | 前回一覧、件数 `…`、読込中表示 | 完了を待つ | component test |
| 条件取得失敗 | 前回一覧、件数 `—`、alert、再試行 | 再試行 | component test / E2E |
| 条件一致0件 | 条件一致0件、このページ0件 | 条件を変更する | E2E |
| ページ範囲外 | 最後の有効ページを再取得 | 閲覧を続ける | component test |
| 狭幅390px | 横スクロールなし、絞り込み操作44px以上 | タッチで条件変更 | E2E |

## UI/UX判定

- 初見理解: 件数ラベルが対象範囲を直接示す。
- アクセシビリティ: 既存button/heading構造を保持し、取得失敗は `alert`、再試行は名前付きbuttonで提供する。
- 視覚階層: 既存一覧見出しの直下へ件数を並べ、一覧操作より強い新しい主操作は追加しない。
- コピー: `全体`、`条件一致（全ページ）`、`このページ`、`前回の表示`で確定値と保持表示を区別する。
- 熟練者効率: 条件変更時の手動ページ戻しを不要にし、取得失敗でも前回の走査位置を失わない。
- 信頼感: 取得中・失敗時に古い件数を新条件の結果として表示しない。
- 反証レビュー: 旧stacked PRをファイル単位で戻すと、現行の生成タイムアウト、wide preview、LLMOps来歴を失うため、現行mainへ対象hunkだけを再実装した。

## 画面証跡

同じ1280×900 viewportと固定fixtureで、旧API契約を再現した画面と現行実装を比較した。`before` は本番データや過去ビルドの画像ではなく、先頭200件だけを返す旧契約を現行画面上で再現したもの。

- [before: 201件中、先頭ページの公開0件として表示される旧契約再現](../evidence/issue-115/before-legacy-contract.png)
- [after: 後続ページの公開項目を全ページ条件1件として表示](../evidence/issue-115/after-server-query.png)

## 検証記録

- Backend全体: 472 passed / 1 skipped
- Backend追加・関連: 19 passed
- Frontend全体: 253 passed / 1 skipped
- Frontend focused: 7 passed
- Frontend typecheck: passed
- Frontend architecture boundary: passed
- Backend architecture / workflow policy: 24 passed
- Playwright server query: 3 passed（390px、44px操作領域、axeを含む）
- Playwright smoke: 12 passed
- Playwright visual (macOS): 9 passed、意図した件数ラベル・操作領域差分でbaseline更新
- Security text scan / agent harness / AI governance: passed
- Linux visual: GitHub Actionsで確認する

## 公開安全性

テストと画面証跡は固定fixtureだけを使い、実ユーザー入力、本番ログ、認証情報、実request・trace・job識別子を含めない。画像は表示内容、PNG形式、寸法、追跡可能な追加metadataの不在を確認した。

## 残るリスク

- suffix / contains検索とfacet集計では、認可範囲内の軽量一覧documentを全件読み出す。数千件規模ではFirestore read量とp95を監視し、必要に応じて検索indexまたは集計用read modelへ移行する。
- 固定mock E2Eは実Firestoreのindex・read costや本番認可設定を検証しない。認可境界はbackend API testで分離して確認する。
- ローカルBackend全体検証はpytest用in-memory Firestore clientを使用し、実Firestore Emulator統合1件はskipした。CIではJava 21とFirestore Emulatorを起動して確認する。
