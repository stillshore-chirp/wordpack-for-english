# AIガバナンス文書インデックス

このディレクトリは、WordPack for EnglishのAIエージェント支援開発で、UI/UX品質、証跡、Issue品質、完了条件を扱う詳細正本です。企業全体のAI統制、法務、倫理審査、モデル監査を意味しません。

エージェントルール全体の配置とCodex・Claude Code・Cursorへの接続は [`docs/agent-harness.md`](../agent-harness.md) を正本とします。

## 読み方

すべての文書を毎回読む必要はありません。

1. ルート `AGENTS.md` と変更対象に最も近い `AGENTS.md` を読む。
2. UI/UX変更では `.agents/skills/ui-ux-review/SKILL.md` を発動する。
3. Skillが対象面を分類し、`02-uiux-review-framework.md` と `03-evidence-and-completion-gates.md` を読む。
4. branch、commit range、Pull Request、未commit差分をreviewする場合は `16-change-scoped-interface-review.md` でbase / headと影響surfaceを確定する。
5. 変更内容に直接関係する詳細文書だけを追加で読む。
6. Issue作成、ルール変更など、UI以外の目的では該当する正本だけを読む。

## 中心文書

| 文書 | 責務 |
|---|---|
| `01-agent-operating-contract.md` | UI/UX作業の基本契約と証跡の考え方 |
| `02-uiux-review-framework.md` | 対象面、品質定義、P0/P1/P2、レビュー観点 |
| `03-evidence-and-completion-gates.md` | 対象面別の証跡と完了条件 |
| `15-interface-engineering-quality.md` | layout、typography、color / theme、icon、motion、視覚的仕上げの実装品質 |
| `16-change-scoped-interface-review.md` | base / head、追加・削除差分、影響surface、変更分類、review-onlyの安全境界 |
| `13-maintenance-policy.md` | ガバナンスとエージェントハーネスの保守 |
| `14-issue-quality-gate.md` | Issueの理由、根拠、現在と目標、受け入れ条件 |

## Product / UX詳細文書

- `04-cognitive-psychology-principles.md`: 認知負荷、初見理解、記憶負荷
- `05-accessibility-and-inclusive-design.md`: native semantics、keyboard、focus、ARIA、form、zoom、reflow、motion preferenceを含むaccessibility
- `06-visual-hierarchy-and-information-architecture.md`: 視覚階層と情報設計
- `07-ui-copy-and-microcopy.md`: copy、label、error message
- `08-state-design-and-error-recovery.md`: state、失敗、回復
- `09-ai-agent-review-protocol.md`: AIレビューの役割分離、変更scope、反証、限界
- `10-utility-user-goal-and-product-fit.md`: ユーザー価値と目的適合
- `11-efficiency-and-expert-use.md`: 熟練者効率と反復利用
- `12-satisfaction-trust-and-emotional-ux.md`: 満足感、安心感、信頼感

## テンプレート

- `templates/uiux-review-report.md`: scope、domain coverage、Introduced / Regression / Pre-existing、verification、verdict
- `templates/state-matrix.md`
- `templates/novice-simulation.md`
- `templates/counter-review.md`
- `templates/user-goal-assessment.md`
- `templates/efficiency-review.md`
- `templates/trust-satisfaction-review.md`
- `templates/completion-gate-report.md`
- `templates/agent-task-prompt.md`

## チェックリスト

- `checklists/p0-p1-p2.md`
- `checklists/accessibility.md`
- `checklists/cognitive-walkthrough.md`
- `checklists/visual-hierarchy.md`
- `checklists/content-stress.md`
- `checklists/interface-engineering.md`
- `checklists/change-scoped-interface-review.md`
- `checklists/utility-user-goal.md`
- `checklists/efficiency.md`
- `checklists/satisfaction-trust.md`

## 機械検証

UI/UXガバナンス自体を変更した場合は、次を実行します。

```bash
bash scripts/verify-ui-quality-governance.sh
bash scripts/verify-agent-harness.sh
bash scripts/verify-ai-governance.sh
```

`verify-ui-quality-governance.sh` は、新しい実装品質・変更差分レビューの正本、Skillからの到達性、証跡形式、外部成果物固有の名称やruntime依存が混入していないことを検査します。

## 原則

UIを見た目だけで評価せず、対象ユーザーが目的を達成でき、stateを理解し、失敗から回復でき、慣れれば効率よく、安心して使えることを評価します。さらに、今回の変更がどのsurfaceへ届き、何を追加・削除し、既存品質を弱めたかをbase / headの証跡で区別します。

主張は、実際の画面、test、DOM / accessibility tree、差分、手動確認、測定結果などの証跡で支えます。sourceだけで確定できないvisual / runtime claimは描画確認するか、Not verifiedと明記します。

本文は日本語を正式版とし、ファイル名、標準名、tool keyword、業界で一般的な用語だけ英語を残します。
