# LLM 評価の実行方法

## オフライン評価

ネットワークや資格情報を使わず、WordPack 本体と Dev / CS / LLM / Business / Common の5カテゴリ例文を検査します。

```bash
python3 scripts/llmops/offline_report.py \
  --json-output /tmp/llmops-offline.json \
  --markdown-output /tmp/llmops-offline.md
```

JSON parse、Pydantic schema、必須 field、語義、例文件数、lemma、語数、日英・文法説明、重複、category / model / provenance、fallback / parse failure 分類を決定的に検査します。サマリーには prompt / model profile / schema の差分、fixture regression 数、baseline 読み込み状態、`Paid LLM requests: 0` を表示します。baseline が欠損・破損している場合は、fixture が通ってもオフライン評価を失敗扱いにします。

fixture を更新する場合は、観測した生成物をそのままコピーせず、[privacy 方針](privacy-and-operations.md)に従って匿名化します。baseline 更新は意図した prompt / schema / model profile 変更をレビューした場合だけ行います。

## Live Evaluation の扱い

外部 LLM を呼ぶ手動 Live Evaluation は、現行 repository で実行履歴、固有の運用 owner、production / model 判断への利用記録を確認できないため廃止しました。品質確認は、ネットワークや資格情報を使わないオフライン評価で行います。
