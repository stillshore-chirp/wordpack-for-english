# 付録: OpenAIモデル設定（Responses API）

本プロジェクトで新規生成に使用できる LLM は `gpt-5.6-luna` だけです。将来の選択肢追加に備えてモデル選択 UI は維持しますが、現在の選択肢と既定値は Luna の 1 件です。バックエンドは Responses API に対して `max_output_tokens` と、必要に応じて `reasoning` / `text` を送信し、旧世代向けの `temperature`、`max_tokens`、`max_completion_tokens` は使用しません。

JSON 生成を強制したい呼び出しでは、Responses API の `text.format={"type":"json_object"}` を使います。`response_format` は Responses API には送信しません。

## 制御できるパラメータ

- `model`: `gpt-5.6-luna`
- `reasoning.effort`: `none` / `low` / `medium` / `high` / `xhigh` / `max`
- `text.verbosity`: `low` / `medium` / `high`
- `text.format`: JSON 生成時に内部で `{"type": "json_object"}` を付与
- `max_output_tokens`: `.env` の `LLM_MAX_TOKENS`

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
- 旧 `gpt-5.4-mini` / `gpt-5.4-nano` や旧 `minimal` は新規リクエストで拒否します。保存済みデータの生成メタ情報は履歴として書き換えません。
- 出力のまとまりや一貫性は `reasoning.effort`、文量や詳細度は `text.verbosity` で調整します。
- JSON 途中切れが疑われる場合は `LLM_MAX_TOKENS` を増やします。
- モデル側が `reasoning` や `text.verbosity` を拒否した場合、バックエンドは JSON 形式指定だけを残して再試行し、それも拒否された場合はプロンプト内の JSON 指示に委ねて再試行します。

仕様は 2026-07-31 時点の [GPT-5.6 Luna モデルページ](https://developers.openai.com/api/docs/models/gpt-5.6-luna) と [モデル選択・移行ガイド](https://developers.openai.com/api/docs/guides/model-guidance?model=gpt-5.6-luna) を基準にしています。
