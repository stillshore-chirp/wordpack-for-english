# LLM 評価の実行方法

## オフライン評価

ネットワークや資格情報を使わず、WordPack 本体と Dev / CS / LLM / Business / Common の5カテゴリ例文を検査します。

```bash
python3 scripts/llmops/offline_report.py \
  --json-output /tmp/llmops-offline.json \
  --markdown-output /tmp/llmops-offline.md
```

JSON parse、Pydantic schema、必須 field、語義、例文件数、lemma、語数、日英・文法説明、重複、category / model / provenance、fallback / parse failure 分類を決定的に検査します。サマリーには prompt / model profile / schema の差分、fixture regression 数、`Paid LLM requests: 0` だけを表示します。

fixture を更新する場合は、観測した生成物をそのままコピーせず、[privacy 方針](privacy-and-operations.md)に従って匿名化します。baseline 更新は意図した prompt / schema / model profile 変更をレビューした場合だけ行います。

## 手動 Live Evaluation

GitHub Actions の `Manual LLM live evaluation` を手動実行します。

`live` では OpenAI SDK retry、provider の parameter fallback、policy retry をすべて無効化し、1 completion を必ず1回の物理 API 試行に固定します。各試行前に request 数と割当済み `max_output_tokens` を予約するため、timeout 後に実行中の request を取り消せない場合も追加試行は行わず、指定した hard limit を超えません。通常運用の生成 retry / fallback には影響しません。

1. まず `mode=estimate` のまま実行します。外部 API request は0件で、case数、想定 request 数、合計 output token budget を確認できます。
2. 実行が必要な場合だけ `mode=live`、`confirm=RUN_PAID_LIVE_EVALUATION` を指定します。
3. 既定は1 case、6 requests、合計25,000 output tokensです。hard limit は5 cases、30 requests、150,000 output tokensで、超過入力は送信前に拒否されます。
4. 結果は Actions step summary と artifact で確認します。finding は informational で、通常CIやdeployを停止しません。

固定金額は表示しません。実行前に request 数と token budget を確認し、現在の公式価格から利用者が判断します。

## GitHub Environment の設定

repository の Settings から Environments を開き、`llm-live-evaluation` を作成します。

1. `Required reviewers` に実行を承認するメンテナを設定します。
2. Environment secret `OPENAI_API_KEY` を登録します。
3. deployment branch / tag rule は、評価を許す ref だけに絞ります。
4. repository-level の通常CI secretには評価用 keyを追加しません。

Environment が未設定でも通常CIとproduction deployには影響しません。Langfuse は live job でも既定で無効です。
