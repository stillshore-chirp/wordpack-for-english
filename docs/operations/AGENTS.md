# Operations AGENTS.md

ルート [`AGENTS.md`](../../AGENTS.md) を先に適用し、この文書は `docs/operations/` 固有の契約だけを追加します。

運用環境の事象を調査・記録する場合は、作業前に [本番環境調査Skill](../../.agents/skills/production-investigation/SKILL.md) を読みます。公開される記録やPR本文を作る場合は、併せて [公開安全性Skill](../../.agents/skills/security-publication/SKILL.md) を適用します。

## 記録方針

- 観測事実、推定、判断、対応、残リスクを分離する。
- Cloud Run logs、Firestore、GitHub Actions、PR、commitなど、確認元を後から追える粒度で記録する。
- secret、token、Cookie、認証header、個人情報、ユーザー入力全文、外部ログ全文を記録しない。
- 本番ログや実データを確認していない内容は、コード上の仮説または未確認事項として書く。
- 公開文書には必要な事実だけを要約し、正確なrevision名、秒単位時刻、完全なquery、実request / trace / job IDを残さない。
- 再発時に直接参照できる恒久的な運用知識だけを残し、一時的な作業メモはIssueまたはprivate logへ分ける。
