# REST API リファレンス

この文書は主要 REST API の一覧と簡単な request / response 例をまとめます。ゲスト公開フラグ API の詳細は [docs/guest_public_api.md](./guest_public_api.md) を正本にします。

## 認証

### `GET /api/config`

frontend が Google login 設定などを取得します。

```json
{
  "request_timeout_ms": 60000,
  "generation_request_timeout_ms": 1500000,
  "llm_model": "gpt-5.6-luna",
  "session_auth_disabled": false,
  "google_client_id": "12345-abcdefgh.apps.googleusercontent.com"
}
```

`request_timeout_ms` は一覧・詳細・更新・ジョブ状態取得など通常APIの上限で、既定は1分です。`generation_request_timeout_ms` は複数のLLM呼び出しを含む生成フロー全体の待機上限で、既定は25分です。フロントエンドは長い値を生成操作だけに使います。

Cloud Run の段階リリース中は、候補 revision を本番経路から識別するため `deployment_version` も返します。このフィールドはデプロイスクリプトが `DEPLOYMENT_VERSION` を設定した環境だけに追加され、未設定時の既存レスポンスは変わりません。

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

### `POST /api/word/pack/jobs`

WordPack生成ジョブを開始し、`202` と `job_id` を返します。アプリUIはこの経路を使い、Firebase Hostingの同期リライト上限を越える生成でも短い状態取得リクエストへ分離します。

Request:

```json
{
  "lemma": "converge",
  "model": "gpt-5.6-luna",
  "reasoning": { "effort": "high" },
  "text": { "verbosity": "medium" },
  "client_job_id": "11111111-1111-4111-8111-111111111111"
}
```

`client_job_id` は任意の UUID です。同じユーザーが同じ値・同じ入力を再送すると既存ジョブを返すため、アプリUIは202応答を受け取れない場合に同じIDで1回だけ再送し、WordPackを重複生成せず状態取得を再開できます。別ユーザー、別種のジョブ、またはfingerprintが異なる別入力で同じIDを使用しようとした場合は409で拒否します。

Response:

```json
{
  "job_id": "wordpack-generation-job:xxxxxxxx",
  "job_type": "wordpack-generation",
  "status": "queued"
}
```

### `GET /api/word/pack/jobs/{job_id}`

作成したユーザーに限り、`queued / running / succeeded / failed` を取得できます。成功時の `result` は保存済みWordPackの `id` と生成内容を含みます。画面再読込後も生成キューがこのAPIで追跡を再開します。

従来の同期 `POST /api/word/pack` は互換性のため残しますが、アプリUIは非同期ジョブ経路を使用します。

入力制約:

- `lemma` は英数字、半角スペース、ハイフン、アポストロフィのみ
- 1〜64 文字
- Firestore path に使えない記号や制御文字は 422

### `POST /api/word/packs`

内容を生成しない空のWordPackを短い同期処理で保存します。Luna Highを待つ用途ではないためLLMは呼び出さず、`sense_title` は見出し語から決定的に初期化します。

### `GET /api/word?lemma=...`

保存済み WordPack から lemma を検索し、定義と例文を返します。未保存なら 404、ゲストが未登録語を検索した場合は 403 です。

### `GET /api/word/packs`

保存済み WordPack の一覧を返します。検索・絞り込み・並び順は、現在の認可範囲全体へ適用してから `offset` / `limit` でページ分割します。ゲスト閲覧では `guest_public=true` の WordPack だけ、`ENFORCE_OWNER_SCOPING=true` のログインユーザーには自分が所有する WordPack だけが認可範囲になります。

Query:

| 名前 | 値 | 既定値 | 意味 |
|---|---|---|---|
| `limit` | 1〜200 | 50 | 1ページの取得上限 |
| `offset` | 0以上 | 0 | 条件適用後の先頭から飛ばす件数 |
| `search` | 128文字以内 | 空 | 見出し語の検索文字列 |
| `search_mode` | `prefix` / `suffix` / `contains` | `contains` | 前方・後方・部分一致 |
| `visibility` | `all` / `public` / `private` | `all` | 公開状態 |
| `generation` | `all` / `generated` / `not_generated` | `all` | 例文生成状態 |
| `sort_key` | `created_at` / `updated_at` / `lemma` / `total_examples` | `created_at` | 並び順の基準 |
| `sort_order` | `asc` / `desc` | `desc` | 昇順または降順 |

Example request:

```http
GET /api/word/packs?visibility=public&limit=200&offset=0
```

Response:

```json
{
  "items": [
    {
      "id": "wp:example-public",
      "lemma": "example",
      "sense_title": "例を示すもの",
      "created_at": "2026-08-28T01:00:00Z",
      "updated_at": "2026-08-28T02:00:00Z",
      "is_empty": false,
      "examples_count": {
        "Dev": 1,
        "CS": 0,
        "LLM": 0,
        "Business": 0,
        "Common": 0
      },
      "checked_only_count": 0,
      "learned_count": 0,
      "guest_public": true
    }
  ],
  "recent_items": [
    {
      "id": "wp:recent",
      "lemma": "recent",
      "sense_title": "最近更新した語義",
      "created_at": "2026-08-20T09:00:00+00:00",
      "updated_at": "2026-08-28T09:00:00+00:00",
      "is_empty": false,
      "examples_count": {"Dev": 1, "CS": 0, "LLM": 0, "Business": 0, "Common": 0},
      "checked_only_count": 0,
      "learned_count": 0,
      "guest_public": false
    }
  ],
  "total": 201,
  "filtered_total": 1,
  "facet_counts": {
    "public": 1,
    "private": 200,
    "generated": 1,
    "not_generated": 0
  },
  "limit": 200,
  "offset": 0
}
```

- `total` は認可範囲全体の件数です。
- `recent_items` は同じ認可範囲から更新日時の新しい順に最大3件を返します。検索・絞り込み条件とページ位置には左右されません。
- `filtered_total` は全検索・絞り込み条件に一致する全ページ件数です。
- `facet_counts.public` / `private` は検索条件と生成状態を保ち、公開状態だけを各値へ切り替えた場合の件数です。
- `facet_counts.generated` / `not_generated` は検索条件と公開状態を保ち、生成状態だけを各値へ切り替えた場合の件数です。
- 同じ並び順の値を持つ項目は WordPack ID で安定化し、同一データに対するページ境界が揺れないようにします。

### `GET /api/word/packs/{id}`

指定 WordPack の詳細を返します。ゲスト閲覧では非公開 WordPack は 404 です。ログイン済みユーザーは既定で legacy shared data を閲覧できますが、`ENFORCE_OWNER_SCOPING=true` では `owner_user_id` の一致を要求します。

新規生成データには `generation_provenance` が含まれ、各例文にも同名 field を持ちます。これは prompt revision、model、usage、fallback、validation、相関情報、hash からなる compact metadata で、raw prompt / output は含みません。導入前の保存データでは空配列です。

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

### `POST /api/word/packs/{id}/examples/{category}/generate/jobs`

保存済み WordPack へカテゴリ別の例文を2件追加するジョブを作り、202 とジョブIDを返します。Luna High の生成が Firebase Hosting の同期上限を越えても、受付済み処理と画面上の失敗表示が食い違わないよう、アプリUIはこちらを使用します。

Request の生成オプションには任意の UUID `client_job_id` を追加できます。同じユーザー・同じジョブ種別・同じ対象WordPack・カテゴリ・生成オプションで再送した場合は既存ジョブを返し、202応答喪失後の追加例文重複を防ぎます。対象または入力が異なる再利用は409です。

### `GET /api/word/packs/{id}/examples/{category}/generate/jobs/{job_id}`

追加例文生成ジョブの `queued / running / succeeded / failed` と、成功時の追加件数を返します。対象 WordPack の所有者だけが取得できます。

従来の同期 `POST /api/word/packs/{id}/examples/{category}/generate` は互換性のため残します。

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

### `POST /api/article/import/jobs`

貼り付けた文章のインポートジョブを作り、202 とジョブIDを返します。生成処理は非同期でタイトル、翻訳、解説、関連 WordPack を保存するため、Firebase Hosting の同期リライト上限を越えても最初のHTTPリクエストを保持しません。

Request:

```json
{
  "text": "English article text...",
  "generation_category": "Common",
  "model": "gpt-5.6-luna",
  "client_job_id": "11111111-1111-4111-8111-111111111111"
}
```

入力上限:

- 1 回のインポート本文は最大 4,000 文字
- 超過時は 413 `article_import_text_too_long`
- `client_job_id` は任意の UUID。同じユーザーが同じ値・同じ文章インポート入力を再送した場合は既存ジョブを返し、202応答の通信断後も重複保存せず状態取得を再開できます。別入力での再利用は409です。アプリUIはPOST前に候補IDを保持し、通信結果不明時は同じIDで1回再送します。確定HTTP失敗は即時エラーとし、再送後も結果不明の場合だけ候補IDを生成キューへ渡します。

### `GET /api/article/import/jobs/{job_id}`

文章インポートジョブの `queued / running / succeeded / failed` を返します。成功時は `article_id` を返し、フロントエンドは記事詳細を取得します。ジョブは作成したユーザーだけが取得できます。

従来の同期 `POST /api/article/import` は互換性のため残しますが、アプリUIは非同期ジョブ経路を使用します。同期ルートはイベントループをブロックする処理を安全に取り消せないため、アプリ内 ASGI timeout の対象外です。直接利用時は Cloud Run のリクエスト期限が最終境界になります。

### `POST /api/article/generate_and_import/jobs`

カテゴリから関連語と例文を生成し、WordPack と Reader 記事へ保存するジョブを作り、202 とジョブIDを返します。Request には任意の UUID `client_job_id` を指定でき、同じユーザー・同じカテゴリ・同じ生成オプションでの再送は既存ジョブを返します。入力が異なる同一IDの再利用は409です。成功時の `result` には `lemma`、`word_pack_id`、`category`、`generated_examples`、`article_ids` が入ります。ジョブは作成したユーザーだけが取得できます。

### `GET /api/article/generate_and_import/jobs/{job_id}`

カテゴリ例文生成・記事化ジョブの `queued / running / succeeded / failed` と、成功時の保存結果を返します。画面移動や一時的な状態取得失敗の後も、生成キューはこのAPIで状態を再確認します。

従来の同期 `POST /api/article/generate_and_import` は互換性のため残します。worker thread 内の保存処理を asyncio のキャンセルで停止できないため、アプリ内 ASGI timeout の対象外です。

一部だけ記事化できた場合は成功結果に警告を含め、全件失敗時はジョブを `failed` にします。

### `GET /api/article`

保存済み Reader 記事の一覧を返します。ゲスト閲覧では `guest_public=true` の記事だけを返します。

### `GET /api/article/{id}`

指定 Reader 記事の詳細を返します。ゲスト閲覧では非公開記事は 404 です。公開記事の関連 WordPack は、ゲスト公開中の WordPack だけを返します。

新規生成記事は `generation_provenance` にタイトル、翻訳、解説、lemma 抽出の呼び出し来歴を持ちます。導入前の保存データでは空配列です。

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

新規生成 Quiz は `generation_provenance` に最終成功呼び出しの来歴を持ちます。導入前の保存データでは空配列です。

新規生成 Quiz は、英文と日本語訳について段落数と各対応段落内の文数が一致した場合だけ保存されます。文対応が一致しない場合はQuiz全体を再生成し、初回生成とJSON修復を含むLLM呼び出し合計5回まで試行します。失敗した生成本文はQuizへ保存しません。

整合確認済みの新規Quizには `translation_alignment_version: "deterministic_v1"` を保存し、表示時も生成時と同じ分割規則を使います。フィールドがない既存Quizは従来の表示分割を維持し、移行・自動再生成しません。

### `POST /api/quiz/generate/jobs` / `GET /api/quiz/generate/jobs/{job_id}`

生成ジョブは次の進捗フィールドを返します。

- `attempt_count`: 実行を開始したLLM呼び出し回数
- `attempt_limit`: 上限。現在は `5`
- `retry_phase`: `generation`、`json_repair`、`translation_alignment` のいずれか
- `error_code`: 失敗時の機械判定用コード

`QUIZ_TRANSLATION_ALIGNMENT_FAILED` は5回試行しても段落別の文数対応が一致しなかったこと、`QUIZ_JSON_PARSE_FAILED` は生成結果のJSON形式を確認できなかったことを示します。試行理由、対象passage・paragraph、英日文数は本文を含めずCloud LoggingとLangfuseの観測メタデータへ記録します。

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

単発リクエストの入力上限:

- OpenAI Speech API の仕様に合わせ、読み上げ対象テキストは最大 4,096 文字
- 超過時は 413 `tts_text_too_long`
- フロントエンドの音声ボタンは、4,096 文字を超える長文を自動分割して順次再生します

## Debug

### `GET /_debug/headers`

FastAPI が受信した Host / X-Forwarded-* / URL / client IP を JSON で返します。Firebase Hosting、Cloud Run、reverse proxy 配下のヘッダ確認に使います。

運用環境でも利用できますが、目立たない debug path として扱い、公開文書には本番 host や request ID の実値を書きません。
