# Frontend AGENTS.md

ルート [`AGENTS.md`](../../AGENTS.md) を先に適用し、この文書は `apps/frontend/` 固有の契約だけを追加します。

## Hard gate

- 画面、操作、表示状態、文言、アクセシビリティ、ユーザーに見えるAPI結果を変える場合は、実装前に [UI/UXレビューSkill](../../.agents/skills/ui-ux-review/SKILL.md) を読む。
- loading、empty、no-results、partial、error、validation-error、disabled、permission-deniedを、該当する範囲で区別する。
- 主要操作はキーボード、可視フォーカス、accessible name、意味のあるrole / labelで利用できるようにする。
- UIの主要操作、フロー、文言が変わる場合は `UserManual.md` の更新要否を確認する。
- 実装詳細だけを検査するテストへ寄せず、利用者から観測できるrole、label、text、状態遷移を優先する。

## 検証

変更範囲に応じて最小十分な組合せを実行する。

```bash
cd apps/frontend && npx tsc -p tsconfig.json
cd apps/frontend && npm test -- --coverage --silent
npx playwright test -c tests/e2e/playwright.config.ts tests/e2e/auth.spec.ts tests/e2e/guest.spec.ts tests/e2e/wordpack.spec.ts
```

- UIのクリティカル導線を変えた場合は、既存Playwright smokeまたは同等のE2Eを更新する。
- screenshot、trace、visual diffを取得した場合は、確認結果と公開安全性をPRへ記録する。
- 未実行項目は理由と残るリスクを報告する。

## Heuristic

- 状態管理、データ取得、描画、業務判断の境界を読み手が追える構造にする。
- 共通化は変更理由が共有される単位で行い、見た目が似ているだけの抽象化を避ける。
- 新しい依存、global state、例外的なDOM操作は、既存手段で解決できない根拠がある場合に追加する。
