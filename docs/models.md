# 付録: OpenAIモデル設定（Responses API）

本プロジェクトで新規生成に使用できる LLM は `gpt-5.6-luna` だけです。将来の選択肢追加に備えてモデル選択 UI は維持しますが、現在の選択肢と既定値は Luna の 1 件です。バックエンドは Responses API に対して `max_output_tokens` と、必要に応じて `reasoning` / `text` を送信し、旧世代向けの `temperature`、`max_tokens`、`max_completion_tokens` は使用しません。

JSON 生成を強制したい呼び出しでは、Responses API の `text.format={"type":"json_object"}` を使います。`response_format` は Responses API には送信しません。

## 制御できるパラメータ

- `model`: `gpt-5.6-luna`
- `reasoning.effort`: `none` / `low` / `medium` / `high` / `xhigh` / `max`
- `text.verbosity`: `low` / `medium` / `high`
- `text.format`: JSON 生成時に内部で `{"type": "json_object"}` を付与
- `max_output_tokens`: `.env` の `LLM_MAX_TOKENS`
- 1試行のタイムアウト: `.env` の `LLM_TIMEOUT_MS`
- 複数呼び出しを含むフロー全体のタイムアウト: `.env` の `LLM_REQUEST_TIMEOUT_MS`

## 設定例

```json
{
  "model": "gpt-5.6-luna",
  "reasoning": { "effort": "high" },
  "text": { "verbosity": "medium" }
}
```

## 運用メモ

- 性能条件を満たす運用基準として `reasoning.effort=high` を既定にします。処理単位で必要な場合だけ UI から別の対応値へ変更できます。
- `reasoning` または `text` の一部だけを API で指定した場合も、欠けている `effort=high` / `verbosity=medium` をアプリ既定として補います。
- 旧 `gpt-5.4-mini` / `gpt-5.4-nano` や旧 `minimal` は新規リクエストで拒否します。保存済みデータの生成メタ情報は履歴として書き換えません。
- 出力のまとまりや一貫性は `reasoning.effort`、文量や詳細度は `text.verbosity` で調整します。
- Luna High の推論時間を確保するため、`LLM_TIMEOUT_MS=300000`（1試行5分）を既定にします。最大4回のLLM呼び出しを直列実行するフローは `LLM_REQUEST_TIMEOUT_MS=1500000`（全体25分）、一覧・詳細・状態取得は `REQUEST_TIMEOUT_MS=60000`（通常1分）へ分離します。サーバーは全体上限+5秒の実動ASGI middlewareで504を返します。ただし、同期処理を worker thread へ移す `/api/article/generate_and_import` は、asyncio のキャンセルで保存処理を停止できないため対象外です。この経路は504返却後の書き込みを避け、Cloud Run の30分以上の期限を最終境界にします。Reader取り込みは非同期ジョブ・ポーリングを使い、Firebase Hosting の同期リライト上限内で各HTTPリクエストを完了させます。Cloud Run は30分以上かつCPUスロットリング無効化を設定します。
- `reasoning.effort=high` では可視出力の前に推論トークンを消費します。`max_output_tokens` は推論・可視出力・非表示の整形トークンを合わせた上限であるため、OpenAI の初期検証時の推奨余裕に合わせて `LLM_MAX_TOKENS=25000` を既定にします。これは予約枠ではなく上限で、実際に生成したトークンだけが課金対象です。
- 応答が `status=incomplete` かつ `incomplete_details.reason=max_output_tokens` になった場合は、使用量を確認して `LLM_MAX_TOKENS` を調整します。コスト管理のため、根拠なくモデル上限の 128,000 まで引き上げません。
- モデル側が `reasoning` や `text.verbosity` を拒否した場合、バックエンドは JSON 形式指定だけを残して再試行し、それも拒否された場合はプロンプト内の JSON 指示に委ねて再試行します。

仕様は 2026-07-31 時点の [GPT-5.6 Luna モデルページ](https://developers.openai.com/api/docs/models/gpt-5.6-luna)、[モデル選択・移行ガイド](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6-luna)、[Reasoning models ガイド](https://developers.openai.com/api/docs/guides/reasoning) を基準にしています。
