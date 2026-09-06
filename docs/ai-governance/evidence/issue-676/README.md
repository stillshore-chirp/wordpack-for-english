# Issue 676 logout state evidence

このスナップショットは、ログアウト結果の失敗・不明・再試行完了時に表示する状態を確認するためのものです。画像にはアプリの表示領域だけを収めています。

- viewport: 1440 × 900
- `before-logout503.png`: canonical base の失敗応答後。従来のサインイン画面が表示される。
- `after-logout503.png`: HTTP 503 を受けた後。個人情報を消去したうえで、ログアウト再試行を案内する。
- `after-logout-unknown.png`: ローカルのテスト用セッションストアで失効処理が完了した後、ブラウザの応答だけが失われた状態。再試行を案内する。
- `after-logout-pending.png`: ログアウト通信の応答待ち。結果未確定のため、polite な status と確認中の操作を表示する。
- `after-logout-retry.png`: 再試行が確認済みとなり、サインイン画面へ戻った状態。

2タブ連携では、同一ブラウザcontextでTab Bのゲスト発行を遅延させ、Tab Aのlogout確認後にTab Bが遅延Cookieを受けて追従ログアウトし、Cookie削除と保護APIの401を確認しました。

同一viewportでの表示確認、実ブラウザの HttpOnly Cookie 挙動、ログアウト状態の状態遷移を検査しました。Cookie値、token、個人情報、認証ヘッダー、本番識別子は画像と説明に含めていません。合成UI応答とローカルテスト用ストアの証跡であり、本番デプロイ、Google OAuth、production Firestore の状態を示すものではありません。
