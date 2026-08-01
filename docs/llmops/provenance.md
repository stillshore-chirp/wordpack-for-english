# Prompt Identity と Generation Provenance

## Prompt Identity

各 operation は次の識別子を持ちます。

| field | 意味 |
|---|---|
| `prompt_id` | 処理の安定した識別子 |
| `operation` | feature と処理名 |
| `prompt_revision` | builder source、参照する helper / 定数 / 既定値、schema revision、主要設定の SHA-256 |
| `schema_revision` | canonicalized schema の SHA-256 |

revision は実際のユーザー入力に依存しません。builder が参照する helper や instruction map の変更も revision に反映されます。prompt 変更ごとの手動 version 更新は不要で、Git 上の builder、参照先、schema が正本です。

## Completion Result

型付き result は本文とは別に、provider、requested / resolved model、requested / effective parameters、fallback profile と理由、response ID / status、input / cached input / output / reasoning / total token、latency、attempt、incomplete 情報、validation、相関 ID、release、Git SHA、Cloud Run revision、input / output hash を保持します。

従来の `complete()` / `complete_text()` は文字列を返す互換 API として残します。test double が usage を持たない場合は値を `null` として扱います。result は呼び出し単位で返し、共有 singleton の `last_result` を使わないため、並行リクエスト間で混線しません。

## 保存場所と失敗時の扱い

- WordPack 本体: `generation_provenance`
- Example: 各 example の `generation_provenance`
- Article / Quiz: 既存 document 内の JSON field

raw prompt / raw output は保存せず、1 entry は 8 KiB を上限にします。serializable でない metadata は warning として記録し、生成物の既存保存処理を継続します。provenance 専用 Firestore collection や追加 write はありません。

本番では deploy script が `DEPLOYMENT_VERSION` と `GIT_SHA` を Cloud Run 設定へ同梱し、Cloud Run が提供する `K_REVISION` と合わせて release を追跡します。
