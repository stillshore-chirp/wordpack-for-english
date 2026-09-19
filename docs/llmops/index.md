# LLMOps

WordPack の生成品質と来歴を、通常の開発・デプロイを重くせずに確認するための入口です。

- [全体像と責務](overview.md)
- [Prompt Identity と Generation Provenance](provenance.md)
- [オフライン評価](evaluation.md)
- [プライバシー、保持、障害調査](privacy-and-operations.md)

通常の PR、`main` への push、本番デプロイでは、評価目的の外部 LLM リクエストは発生しません。CI に表示される LLMOps 情報は短いオフラインサマリーだけで、オフライン評価はマージ条件ではありません。
