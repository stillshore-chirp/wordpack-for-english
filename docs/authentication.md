# 認証とセッション

この文書は Google OAuth セットアップ、ログイン/ゲストセッション、Cookie、認証失敗時の確認、ログキーをまとめます。環境変数の詳細は [docs/環境変数の意味.md](./環境変数の意味.md) を参照してください。

## 構成

- frontend は Google Identity Services で ID token を取得します。
- backend は `/api/auth/google` で ID token または GIS `credential` を検証し、HttpOnly の署名付きセッション Cookie を発行します。
- frontend は ID token を長期保存せず、表示用の認証状態だけを local storage に保存します。未解決のログアウト状態がない場合、再読み込み時は保存済みの表示状態を初期表示に使い、認証を要する API は HttpOnly Cookie で backend に確認します。
- ゲスト閲覧は `/api/auth/guest` で署名付きゲスト Cookie を発行し、読み取り専用 API だけを許可します。
- ログアウトは `/api/auth/logout` で通常セッションとゲストセッションを失効させ、Cookie の削除を指示します。対応するセッションがすでにない場合も backend は HTTP 204 を返します。frontend は server-side session の失効を HTTP 200 または 204 の応答で確認できた場合だけ、ログアウト完了として扱います。
- Cookie の署名 payload は opaque な `sid` のみで、ユーザー ID やゲスト状態は Firestore の `sessions/{sid}` で検証します。

## Google OAuth クライアント作成

1. Google Cloud Console で対象プロジェクトを作成または選択します。
2. OAuth 同意画面でアプリ名、サポートメール、必要なドメインを設定します。
3. 認証情報から OAuth クライアント ID を作成し、種類は Web application を選びます。
4. 承認済み JavaScript 生成元に `http://127.0.0.1:5173` と `http://localhost:5173` を追加します。
5. 承認済みリダイレクト URI に同じローカル origin を追加します。
6. 発行された client ID を backend と frontend の設定に入れます。
7. JSON secret をダウンロードする場合は安全な場所に保管し、リポジトリには追加しません。

ローカル設定例:

```env
GOOGLE_CLIENT_ID=12345-abcdefgh.apps.googleusercontent.com
GOOGLE_ALLOWED_HD=example.com
ADMIN_EMAIL_ALLOWLIST=<admin-email>
SESSION_SECRET_KEY=<32文字以上の乱数>
```

frontend:

```env
VITE_GOOGLE_CLIENT_ID=12345-abcdefgh.apps.googleusercontent.com
```

本番ビルド時に `VITE_GOOGLE_CLIENT_ID` が空でも、backend の `/api/config` が `google_client_id` を返す環境では Google ログインボタンを初期化できます。

## 通常ログイン

1. ユーザーが「Googleでログイン」を押します。
2. Google の popup で account を選びます。
3. frontend が Google から受け取った credential を `/api/auth/google` へ送ります。既存互換として `{ "id_token": "..." }` も受け付けます。
4. backend が token、audience、email、email verification、hosted domain、allowlist を検証します。
5. GIS の `credential` と `g_csrf_token` を使う場合は、body と `g_csrf_token` Cookie の値が一致しないリクエストを拒否します。
6. 成功時、backend が Firestore に server-side session を作成し、Cookie には署名済み `sid` だけを入れて返します。
7. frontend はユーザー表示情報だけを local storage に保存します。

`ADMIN_EMAIL_ALLOWLIST` が空の場合、開発/テストでは許可リストによる制限は無効です。本番では空のまま起動しないよう設定バリデーションで止めます。

## ゲスト閲覧

ゲスト閲覧はログイン不要の読み取り専用モードです。

- 開始: `POST /api/auth/guest`
- 終了: `POST /api/auth/logout`
- 閲覧可能: `guest_public=true` の WordPack、公開 WordPack に紐づく例文、`guest_public=true` の Reader 記事、`guest_public=true` の Quiz
- 禁止: 生成、再生成、削除、保存、音声再生、書き込み API

ゲスト公開フラグ API の詳細は [docs/guest_public_api.md](./guest_public_api.md) を参照してください。

## ログアウトの結果と再試行

`POST /api/auth/logout` は、通常ログインとゲスト閲覧のどちらでも使います。backend の正常応答は `204 No Content` で、通常セッション、ゲストセッション、`__session` の削除を指示します。対応するセッションがすでにない場合も同じ応答になるため、ログアウトは再試行に対して冪等です。失効処理を保存できない場合は `500` になり、frontend は server-side session の失効を確認済みとは表示しません。

frontend は HTTP `200` または `204` のときだけ `confirmed` として扱い、それ以外の HTTP status は `failed` として扱います。通信例外、Abort、応答を受け取れない場合は `unknown` です。ログアウト開始時点で画面に保持していたユーザー情報と local auth payload を削除し、結果が `failed` または `unknown` なら未解決状態を保存します。HttpOnly Cookie は JavaScript から読み書きできないため、frontend は Cookie を JavaScript で削除せず、server-side session の失効を backend 応答で判断します。

ログアウト開始後は進行中のセッション発行要求の完了を待ち、その収束や logout 応答の待機がタイムアウトした場合は `unknown` として再試行を案内します。

別タブのログアウトと、受信側タブが開始したセッション発行が重なった場合は、発行が通知前に完了していても通知だけで `confirmed` とせず、受信側タブ自身が logout を再確認します。再確認が未確定の間は `unknown` を保持して再試行を案内します。

利用できる保存領域と別タブ通知を使って未解決状態を共有します。安全に共有できる手段がない場合は、結果未確認（`unknown`）を維持して再試行を案内します。

過去のログアウト確認を参照できない新しいタブでは、サーバー側の終了を確認するまでログインやゲスト閲覧を開始せず、「ログアウトを再試行」から確認します。

`failed` または `unknown` の間は未解決状態を保持し、再読み込み後も認証済みの表示を復元せず、ログアウトの再試行を案内します。再試行は、前回の失効が済んでいる場合や有効なセッションが残っていない場合も `204` で確認できます。再試行が確認済みになると未解決状態を解消して匿名状態へ戻ります。未解決のログアウトを残したまま、ゲスト開始で確認済みのログアウトとして扱うことはありません。

## Cookie

通常セッション:

- `SESSION_COOKIE_NAME` の既定は `wp_session`
- Firebase Hosting rewrite 経由でも届くよう、同じ token を `__session` にも配信します。
- `wp_session` と `__session` の両方がある場合は通常セッションを優先します。

ゲストセッション:

- `GUEST_SESSION_COOKIE_NAME` の既定は `wp_guest`
- 同じく `__session` にも配信します。
- ログイン後に `wp_guest` が残っても、通常セッションが有効ならゲスト扱いにはしません。

共通:

- Cookie は HttpOnly です。
- `SESSION_COOKIE_SECURE` は本番 HTTPS では true を指定します。
- backend がログアウトを正常処理した場合は、通常セッション、ゲストセッション、`__session` の削除を指示し、対応する server-side session を revoke します。対応するセッションがすでにない場合も `204` を返します。
- HttpOnly Cookie は JavaScript から削除できません。frontend のローカル消去は画面上の情報を安全に片付けるためのもので、server-side session の失効確認を代替しません。
- 絶対期限に加えて idle timeout を検証し、`last_seen_at` は設定された間隔より頻繁には更新しません。

## CSRF 防御

- unsafe method (`POST`, `PUT`, `PATCH`, `DELETE`) では Fetch Metadata (`Sec-Fetch-Site`) と `Origin` を確認します。
- 明示的な cross-site unsafe request は 403 です。
- `Origin` がある場合は、同一 origin、`CORS_ALLOWED_ORIGINS`、または `CSRF_TRUSTED_ORIGINS` に含まれる origin だけを許可します。
- `CSRF_PROTECTION_ENABLED=false` は本番環境では起動時に拒否されます。
- ブラウザ外のクライアントや TestClient のように `Origin` がない unsafe request は、Fetch Metadata で cross-site と示されない限り許可します。

## 認証失敗時の確認

ユーザー向け表示と backend ログを分けて確認します。

| 症状 | 主な確認 |
|---|---|
| ID token が取得できない | frontend 設定、`VITE_GOOGLE_CLIENT_ID`、Google popup、`google_login_missing_id_token` |
| backend が 500 を返す | `GOOGLE_CLIENT_ID` 未設定、backend 設定ロード、`/api/config` |
| 403 email not allowlisted | `ADMIN_EMAIL_ALLOWLIST` に対象メールが含まれるか |
| 403 email unverified | Google アカウントのメール確認が済んでいるか |
| domain mismatch | `GOOGLE_ALLOWED_HD` と ID token の hosted domain が一致するか |
| session が復元されない | Cookie 名、Secure 属性、Hosting rewrite、`__session`、ブラウザ Cookie 設定 |
| 403 CSRF check failed | `Origin`, `Sec-Fetch-Site`, `CORS_ALLOWED_ORIGINS`, `CSRF_TRUSTED_ORIGINS` |

## 構造化ログキー

Google 認証まわりでは次の key を確認します。

| key | 意味 |
|---|---|
| `event` | `google_auth_failed`, `google_auth_denied`, `google_auth_succeeded` など |
| `reason` | `invalid_token`, `missing_claims`, `domain_mismatch`, `email_not_allowlisted`, `email_unverified` など |
| `error` | Google SDK から受け取った例外の要約 |
| `missing_claims` | 欠落していた claim の配列 |
| `hosted_domain` | ID token の `hd` 値 |
| `allowed_domain` | 設定された許可 domain |
| `email_hash` | メールアドレスをハッシュ化した照合用値 |
| `display_name_hash` | 表示名をハッシュ化した照合用値 |

平文のメールアドレスや表示名は Cloud Logging に出さず、ハッシュ値で突き合わせます。

## セキュリティメモ

- `SESSION_SECRET_KEY` は 32 文字以上の十分に乱数性のある値を使います。
- `change-me` など既知のサンプル値は使いません。
- Google OAuth client secret、service account JSON、Cookie、ID token はリポジトリへコミットしません。
- 本番では `CORS_ALLOWED_ORIGINS` と `ALLOWED_HOSTS` を明示し、ワイルドカードのままにしません。
- 本番では `DISABLE_SESSION_AUTH=true` と `CSRF_PROTECTION_ENABLED=false` は起動時に拒否されます。
- 認証エラー調査では token 原文、Cookie、request ID の実値を公開文書や PR 本文へ書きません。
