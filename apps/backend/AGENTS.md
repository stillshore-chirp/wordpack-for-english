# Backend AGENTS.md

ルート [`AGENTS.md`](../../AGENTS.md) を先に適用し、この文書は `apps/backend/` 固有の契約だけを追加します。

## Hard gate

- API の request、response、HTTP status、認証・認可、永続化契約を変える場合は、関連する API 文書と契約テストを同じ変更内で確認する。
- 例外を黙殺せず、原因、影響、再試行可否を呼び出し側が判断できる形にする。
- ログへ secret、token、Cookie、認証 header、PII、ユーザー入力全文を出さない。
- 本番挙動を述べる場合は、[本番環境調査 Skill](../../.agents/skills/production-investigation/SKILL.md) の証跡条件に従う。
- 不具合修正では、外から観測できる失敗条件を固定する回帰テストを原則として追加する。

## 検証

変更範囲に応じて最小十分な組合せを実行します。

```bash
PYTHONPATH=apps/backend pytest
PYTHONPATH=apps/backend pytest -q --no-cov tests/test_security_headers.py
```

- DB、外部 API、非同期処理、認証境界を変えた場合は、必要な Integration / contract test を追加する。
- Cloud Run 設定、workflow、deploy / promote script を変える場合は、[`docs/operations/AGENTS.md`](../../docs/operations/AGENTS.md) の検証ゲートも適用する。
- 未実行項目は理由と残るリスクを報告する。

## Heuristic

- Presentation、Application、Domain、Infrastructure の依存方向を保ち、外部技術の詳細をドメイン判断へ漏らさない。
- 抽象化は差し替え、契約固定、テスト容易性に実益がある境界へ置く。
- fallback は利用者影響を減らす場合に限定し、根本原因やデータ不整合を隠さない。
