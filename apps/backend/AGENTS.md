# Backend AGENTS.md

ルート [`AGENTS.md`](../../AGENTS.md) を先に適用し、この文書は `apps/backend/` 固有の契約だけを追加します。

## Hard gate

- APIのrequest、response、HTTP status、認証・認可、永続化契約を変える場合は、関連するAPI文書と契約テストを同じ変更内で確認する。
- 例外を黙殺せず、原因、影響、再試行可否を呼び出し側が判断できる形にする。
- ログへsecret、token、Cookie、認証header、PII、ユーザー入力全文を出さない。
- 本番挙動を述べる場合は、[本番環境調査Skill](../../.agents/skills/production-investigation/SKILL.md)の証跡条件に従う。
- 不具合修正では、外から観測できる失敗条件を固定する回帰テストを原則として追加する。

## 検証

変更範囲に応じて最小十分な組合せを実行する。

```bash
PYTHONPATH=apps/backend pytest
PYTHONPATH=apps/backend pytest -q --no-cov tests/test_security_headers.py
```

- DB、外部API、非同期処理、認証境界を変えた場合は、必要なIntegration / contract testを追加する。
- Cloud Run設定やdeploy scriptを変えた場合は、対応するshellcheckとdry-runを実行する。
- 未実行項目は理由と残るリスクを報告する。

## Heuristic

- Presentation、Application、Domain、Infrastructureの依存方向を保ち、外部技術の詳細をドメイン判断へ漏らさない。
- 抽象化は差し替え、契約固定、テスト容易性に実益がある境界へ置く。
- fallbackは利用者影響を減らす場合に限定し、根本原因やデータ不整合を隠さない。
