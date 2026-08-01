# LLMOps の全体像

## 目的

プロンプト、schema、モデル設定を変更したときに、無料の契約検査を日常利用し、必要なときだけ明示的に有料評価を実行できるようにします。本番生成では、後から変更点と失敗箇所を追える compact metadata を既存データへ同梱します。

```text
Git 上の prompt / schema / model profile
  -> 通常 CI の fixture 契約検査（外部 request 0）
  -> 任意の手動 estimate / live evaluation
  -> 本番の generation provenance と構造化ログ
  -> 問題ケースを匿名化 fixture へ還流
```

## 責務分担

| 領域 | 責務 |
|---|---|
| `backend.infrastructure.llm.prompts` | prompt の正本。外部サービスから runtime fetch しない |
| `backend.llmops.identity` | builder source と参照する helper / 定数、schema、主要設定から revision を計算 |
| `backend.llmops.types` / `completion` | 型付き completion、相関情報、compact provenance |
| provider | Responses API metadata、usage、parameter fallback、`store=False` |
| WordPack / Example / Article / Quiz 保存 | provenance を既存 write に同梱。専用 collection は作らない |
| `evals/` / `scripts/llmops/` | fixture、deterministic evaluator、estimate、レポート |
| Langfuse / Cloud Logging | 任意の詳細観測。生成処理の成功条件にはしない |

## 通常運用を維持する根拠

- `CI` は `offline_report.py` だけを実行し、live script、OpenAI key、Langfuse keyを参照しません。
- オフラインサマリーは backend job の Python 3.14 側で1回だけ実行し、`continue-on-error` です。pytest など通常の品質検査は従来どおり必須です。
- Live Evaluation workflow は `workflow_dispatch` だけを trigger とし、production deploy から参照されません。
- production deploy は従来の `main` / 手動 trigger、候補 revision、canary、昇格・rollback 経路を維持します。評価用 LLM 呼び出しは含みません。
- 生成時の来歴は、既存の LLM 呼び出し結果から作り、追加 LLM 呼び出しを行いません。保存も既存 Firestore write へ同梱します。

レポートを開かず、Live Evaluation を一度も実行せず、従来どおり PR をマージしてデプロイできます。品質 finding は比較材料であり required check や自動 rollback 条件ではありません。
