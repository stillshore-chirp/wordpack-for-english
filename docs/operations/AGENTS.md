# Operations AGENTS.md

ルート [`AGENTS.md`](../../AGENTS.md) を先に適用し、この文書は本番運用、デプロイ、関連 workflow・script 固有の契約だけを追加します。

運用環境の事象を調査・記録する場合は、作業前に [本番環境調査 Skill](../../.agents/skills/production-investigation/SKILL.md) を読みます。公開される記録や PR 本文を作る場合は、併せて [公開安全性 Skill](../../.agents/skills/security-publication/SKILL.md) を適用します。

## Hard gate

- 本番ログや実データを確認していない内容を、本番で観測した事実として扱わない。
- secret、token、Cookie、認証 header、個人情報、ユーザー入力全文、外部ログ全文を記録・公開しない。
- production deploy、traffic 変更、rollback、secret・権限変更は、明示された権限の範囲内だけで実行する。
- workflow、deploy / promote script、Cloud Run 設定を変えた場合は、対象に対応する構文検査、shellcheck、契約テスト、dry-run を実行する。
- 実行できない検証は、理由と残るリスクを PR と最終報告へ記録する。

## デプロイ関連の検証

Cloud Run の deploy script または関連設定を変更した場合は、少なくとも次を実行します。

```bash
shellcheck scripts/deploy_cloud_run.sh scripts/promote_cloud_run_revision.sh
./scripts/deploy_cloud_run.sh \
  --dry-run \
  --env-file configs/cloud-run/ci.env \
  --project-id ci-placeholder-project \
  --region asia-northeast1 \
  --service wordpack-backend
```

- 変更していない script を shellcheck 対象から外すことはできますが、変更対象の script は必ず含めます。
- `.github/workflows/**` を変えた場合は YAML 構文、permissions、branch / path 条件、secret 参照、関連する workflow 契約テストを確認します。
- 本番操作を伴わない PR では dry-run と契約テストを使い、本番デプロイ済みと表現しません。

## 記録方針

- 観測事実、推定、判断、対応、残リスクを分離する。
- Cloud Run logs、Firestore、GitHub Actions、PR、commit など、確認元を後から追える粒度で記録する。
- 公開文書には必要な事実だけを要約し、正確な revision 名、秒単位時刻、完全な query、実 request / trace / job ID を残さない。
- 再発時に直接参照できる恒久的な運用知識だけを残し、一時的な作業メモは Issue または private log へ分ける。
