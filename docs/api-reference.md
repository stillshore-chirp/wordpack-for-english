# REST API リファレンス

この文書は主要 REST API の一覧と簡単な request / response 例をまとめます。ゲスト公開フラグ API の詳細は [docs/guest_public_api.md](./guest_public_api.md) を正本にします。

## 認証

### `GET /api/config`

frontend が Google login 設定などを取得します。

```json
{
  "google_client_id": "12345-abcdefgh.apps.googleusercontent.com"
}
```

### `POST /api/auth/google`

Google Identity Services の ID token または `credential` を backend に渡し、通常セッション Cookie を発行します。Cookie には署名済みの opaque `sid` のみを入れ、session 実体は backend の server-side store で検証します。

Request:

```json
{
  "id_token": "<google-id-token>"
}
```

GIS `credential` 形式:

```json
{
  "credential": "<google-credential>",
  "g_csrf_token": "<csrf-token-from-g_csrf_token-cookie>"
}
```

Response:

```json
{
  "user": {
    "email": "<user-email>",
    "name": "<display-name>"
  }
}
```

実際の token、Cookie、個人情報はログや公開文書に残しません。

### `POST /api/auth/guest`

署名済みゲストセッション Cookie を発行し、閲覧専用モードを開始します。

Response:

```json
{
  "mode": "guest"
}
```

### `POST /api/auth/logout`

通常ログインまたはゲスト閲覧のセッション Cookie を削除し、server-side session を revoke して匿名状態へ戻します。

## WordPack

### `POST /api/word/pack`

WordPack を生成し、語義、共起、対比、例文、語源、学習カード要点、発音などを返します。

Request:

```json
{
  "lemma": "converge",
  "model": "gpt-5.4-mini",
  "reasoning": { "effort": "minimal" },
  "text": { "verbosity": "medium" }
}
```

Response:

```json
{
  "id": "wp:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "lemma": "converge",
  "senses": [],
  "examples": {},
  "citations": [],
  "confidence": "medium"
}
```

入力制約:

- `lemma` は英数字、半角スペース、ハイフン、アポストロフィのみ
- 1〜64 文字
- Firestore path に使えない記号や制御文字は 422

### `GET /api/word?lemma=...`

保存済み WordPack から lemma を検索し、定義と例文を返します。未保存なら 404、ゲストが未登録語を検索した場合は 403 です。

### `GET /api/word/packs`

保存済み WordPack の一覧を返します。ゲスト閲覧では `guest_public=true` の WordPack だけを返します。

### `GET /api/word/packs/{id}`

指定 WordPack の詳細を返します。ゲスト閲覧では非公開 WordPack は 404 です。ログイン済みユーザーは既定で legacy shared data を閲覧できますが、`ENFORCE_OWNER_SCOPING=true` では `owner_user_id` の一致を要求します。

### `DELETE /api/word/packs/{id}`

指定 WordPack を削除します。ログイン済みユーザーのみ利用できます。

### `POST /api/word/packs/{id}/guest-public`

WordPack のゲスト公開フラグを更新します。詳細は [docs/guest_public_api.md](./guest_public_api.md) を参照してください。

Request:

```json
{
  "guest_public": true
}
```

## 例文

### `GET /api/word/examples`

保存済み例文を WordPack 横断で返します。ゲスト閲覧では、`guest_public=true` の WordPack に紐づく例文だけを返します。

### `POST /api/word/examples/bulk-delete`

例文 ID の配列を受け取り、一括削除します。

Request:

```json
{
  "ids": [1, 2]
}
```

### `POST /api/word/examples/{id}/transcription-typing`

指定 ID の例文について、文字起こし練習で入力した文字数を検証・加算します。

Request:

```json
{
  "input_length": 26
}
```

## Article import

### `POST /api/article/import`

貼り付けた文章を保存し、タイトル、翻訳、解説、関連 WordPack を生成します。

Request:

```json
{
  "text": "English article text...",
  "generation_category": "Common",
  "model": "gpt-5.4-mini"
}
```

入力上限:

- 1 回のインポート本文は最大 4,000 文字
- 超過時は 413 `article_import_text_too_long`

### `POST /api/article/generate_and_import`

カテゴリから例文を生成し、記事として保存します。一部だけ記事化できた場合は成功レスポンスに警告を含め、全件失敗時は 502 を返します。

### `GET /api/article`

保存済み Reader 記事の一覧を返します。ゲスト閲覧では `guest_public=true` の記事だけを返します。

### `GET /api/article/{id}`

指定 Reader 記事の詳細を返します。ゲスト閲覧では非公開記事は 404 です。公開記事の関連 WordPack は、ゲスト公開中の WordPack だけを返します。

### `POST /api/article/{id}/guest-public`

Reader 記事のゲスト公開フラグを更新します。

Request:

```json
{
  "guest_public": true
}
```

## Quiz

Quiz API は保存済み WordPack や lemma から長文読解 Quiz を生成、保存、取得、削除、採点 attempt 保存するために使います。

主な契約:

- `format_profile`: 出題構造
- `generation_domain`: 題材
- `domain_intensity`: 専門性の強さ
- ゲスト閲覧では公開済み Quiz の閲覧とローカル採点のみ許可

### `GET /api/quiz`

保存済み Quiz の一覧を返します。ゲスト閲覧では `guest_public=true` の Quiz だけを返します。

### `GET /api/quiz/{id}`

指定 Quiz の詳細を返します。ゲスト閲覧では非公開 Quiz は 404 です。Attempt 保存はログイン済みユーザーのみ利用できます。

### `POST /api/quiz/{id}/guest-public`

Quiz のゲスト公開フラグを更新します。

Request:

```json
{
  "guest_public": true
}
```

## Text-to-Speech

### `POST /api/tts`

OpenAI gpt-4o-mini-tts で読み上げた音声を `audio/mpeg` として返します。

Request:

```json
{
  "text": "Example sentence.",
  "voice": "alloy"
}
```

入力上限:

- 読み上げ対象テキストは最大 500 文字
- 超過時は 413 `tts_text_too_long`

## Debug

### `GET /_debug/headers`

FastAPI が受信した Host / X-Forwarded-* / URL / client IP を JSON で返します。Firebase Hosting、Cloud Run、reverse proxy 配下のヘッダ確認に使います。

運用環境でも利用できますが、目立たない debug path として扱い、公開文書には本番 host や request ID の実値を書きません。
