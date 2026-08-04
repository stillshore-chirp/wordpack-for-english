# LLMOps のプライバシーと障害調査

## 記録方針

production 既定では prompt / output 全文を Langfuse と Cloud Logging へ送らず、文字数と SHA-256 hash を記録します。Responses API request は `store=False` を明示します。認証情報は provenance、fixture、report、構造化ログへ保存しません。

raw content が本当に必要な限定調査では、`LANGFUSE_LOG_FULL_PROMPT` と `LANGFUSE_LOG_FULL_OUTPUT` を個別に opt-in し、最大文字数も指定します。調査前にデータ分類、閲覧者、保持期間、削除方法を決め、終了後は設定を `false` へ戻します。production のサンプル設定は両方 `false` です。

Langfuse を使わない場合は `LANGFUSE_ENABLED=false` とします。初期化・span update・provenance serialization・任意レポート生成の失敗は warning とし、本来の生成と保存を失敗させません。

## 保持と redaction

- hash は同一内容の相関用で、raw content の代替復元情報として扱いません。
- provenance は生成物と同じ retention / delete lifecycle に従います。
- Actions artifact の保持期間は repository の artifact retention 設定に従い、不要になった artifact は削除します。
- 本番入力、個人情報、秘密情報、request / trace / job ID の実値を fixture や公開 Issue / PR へ転記しません。

## 障害調査

1. 保存済み生成物の `prompt_revision`、requested / resolved model、effective parameters、fallback、usage、release を確認します。
2. 同じ `request_id` / `workflow_id` / `trace_id` を private な Cloud Logging / Langfuse 内で相関します。
3. `release`、`git_sha`、`cloud_run_revision` から変更境界を確認します。
4. `validation` と input / output hash で parse、schema、application のどこで失敗したかを絞ります。
5. 本番ログや実データを未確認なら、コード上の仮説として扱い、原因を断定しません。

WordPack 生成では、型検証後に文字列の前後空白を除き、空白だけの配列要素と不完全な比較要素を保存前に除去します。意味上必須の本文が空白だけの場合は application validation 失敗を維持します。正規化・拒否ログは件数、reason code、フィールド種別だけを記録し、raw output は記録しません。Live Evaluation も同じ正規化境界を使います。

## 本番問題を fixture へ還流する

1. private な証跡から再現に必要な構造だけを抽出します。
2. 固有名詞、ユーザー入力、ID、日時、URL、認証情報を架空値へ置換します。
3. hash や request / trace / job ID の実値も再利用せず、固定の短い test value に置き換えます。
4. issue の期待契約を `expected` に書き、修正前に evaluator が finding を返すことを確認します。
5. 修正後のオフラインレポートと関連 unit test を残し、raw evidence は Git に追加しません。
