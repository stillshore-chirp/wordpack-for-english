# ゲスト公開フラグ API

## 概要
- **公開範囲**: WordPack 単位で `guest_public` を管理します。
- **例文の扱い**: 例文は WordPack に紐づくため、WordPack が公開なら例文も公開されます。
- **Reader / Quiz の扱い**: Reader 記事と Quiz はそれぞれのドキュメントに `guest_public` を持ち、コンテンツ単位で公開/非公開を切り替えます。
- **拡張余地**: 例文単位で公開制御が必要になった場合は `examples` コレクション側へ `guest_public` を追加する設計に拡張可能です。

## 権限
- **更新**: ログイン済みユーザーのみ許可（ゲスト/匿名は拒否）。
- **閲覧（ゲスト）**: `guest_public=true` の WordPack / Reader 記事 / Quiz と、公開 WordPack に紐づく例文のみ返却。
- **終了（ゲスト）**: `POST /api/auth/logout` でゲストセッション Cookie を失効し、匿名状態へ戻します。
- **非公開詳細**: ゲストが非公開 WordPack / Reader 記事 / Quiz を直接指定した場合は 404 を返し、存在有無を隠します。
- **未登録 lemma**: ゲストが未登録 lemma を検索しても WordPack は生成せず、403 を返します。
- **書き込み**: ゲストの unsafe request は 403 です。公開 Quiz のローカル採点表示は frontend 側で可能ですが、Attempt 保存 API はログイン済みユーザーのみ許可します。
- **所有者**: 新規作成される WordPack / Reader 記事 / Quiz / Quiz Attempt は `owner_user_id` を保存します。既存データの `owner_user_id` が空の場合は既定で legacy shared data として扱い、`ENFORCE_OWNER_SCOPING=true` のときだけ所有者一致を強制します。

## API

### WordPack 公開フラグ更新
`POST /api/word/packs/{word_pack_id}/guest-public`

**Request**
```json
{
  "guest_public": true
}
```

**Response**
```json
{
  "word_pack_id": "wp:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "guest_public": true
}
```

**メモ**
- 更新後は `word_packs.metadata.guest_public` が保存されます。
- 監査用の構造化ログに `event`, `word_pack_id`, `user_id` を記録します。

### Reader 記事公開フラグ更新
`POST /api/article/{article_id}/guest-public`

**Request**
```json
{
  "guest_public": true
}
```

**Response**
```json
{
  "article_id": "article:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "guest_public": true
}
```

**メモ**
- 更新後は `articles.guest_public` が保存されます。
- ゲスト詳細では、記事に紐づく関連 WordPack のうち `guest_public=true` のものだけを返します。

### Quiz 公開フラグ更新
`POST /api/quiz/{quiz_id}/guest-public`

**Request**
```json
{
  "guest_public": true
}
```

**Response**
```json
{
  "quiz_id": "quiz:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "guest_public": true
}
```

**メモ**
- 更新後は `quizzes.guest_public` が保存されます。
- ゲスト閲覧では公開 Quiz の詳細表示とローカル採点だけを許可します。Attempt 保存は許可しません。

### ゲスト閲覧時のフィルタ
`GET /api/word/packs`

- ゲスト閲覧モードの場合は `guest_public=true` の WordPack のみ返却されます。
- `GET /api/word/packs/{word_pack_id}` と `GET /api/word?lemma=...` も同様に非公開の WordPack は 404 で返却されます。

`GET /api/word/examples`

- ゲスト閲覧モードの場合は、`guest_public=true` の WordPack に紐づく例文だけを返します。

`GET /api/article` / `GET /api/article/{article_id}`

- ゲスト閲覧モードの場合は、`guest_public=true` の Reader 記事だけを返します。
- 非公開記事の詳細は 404 で返却されます。

`GET /api/quiz` / `GET /api/quiz/{quiz_id}`

- ゲスト閲覧モードの場合は、`guest_public=true` の Quiz だけを返します。
- 非公開 Quiz の詳細は 404 で返却されます。
