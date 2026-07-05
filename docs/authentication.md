# 認証とセッション

この文書は Google OAuth セットアップ、ログイン/ゲストセッション、Cookie、認証失敗時の確認、ログキーをまとめます。環境変数の詳細は [docs/環境変数の意味.md](./環境変数の意味.md) を参照してください。

## 構成

- frontend は Google Identity Services で ID token を取得します。
- backend は `/api/auth/google` で ID token または GIS `credential` を検証し、HttpOnly の署名付きセッション Cookie を発行します。
- frontend は ID token を長期保存しません。再読み込み時は Cookie と `/api/config` の応答から認証状態を再構築します。
- ゲスト閲覧は `/api/auth/guest` で署名付きゲスト Cookie を発行し、読み取り専用 API だけを許可します。
- ログアウトは `/api/auth/logout` で通常セッションとゲストセッションを失効させます。
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
- ログアウト時は通常セッション、ゲストセッション、`__session` を削除し、対応する server-side session を revoke します。
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
