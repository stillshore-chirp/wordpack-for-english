---
name: ui-ux-review
description: "アプリ本体またはリポジトリが制御する独自UIの変更・レビューで、変更scope、ユーザー価値、状態、アクセシビリティ、実装品質、熟練者効率、信頼感を証跡付きで確認する。"
---

# UI/UXレビュー Skill

## 1. 発動条件と対象面

次の変更で使います。

- 画面、ページ、component、layout、navigation、form
- 表示文言、label、説明、error、notification
- loading、empty、no-results、partial、error、validation-error、disabled、permission-denied
- accessibility、responsive、typography、color、theme、motion、icon、操作方法
- backend変更でも、利用者に見える結果、状態、回復方法が変わるもの
- 未commit差分、branch、commit range、Pull Requestに対するUI/UXレビュー

最初に [`docs/ai-governance/02-uiux-review-framework.md`](../../../docs/ai-governance/02-uiux-review-framework.md) で対象面を分類します。

- **アプリ本体UI**: リポジトリがlayout、操作、状態、focus、accessibilityを実装する画面。本文書の全手順を適用する。
- **GitHub共同作業面**: Issue / PR template、repository Markdown、workflow説明など。リポジトリが制御する文言、構造、表示、link、公開安全性だけを範囲に比例して確認する。
- **混在**: 両方を別々に確認し、一方の証跡で他方を代用しない。

## 2. 読む正本

- 全作業: `AGENTS.md` と変更対象に最も近い `AGENTS.md`
- UI品質・P0/P1/P2: `docs/ai-governance/02-uiux-review-framework.md`
- 証跡・完了条件: `docs/ai-governance/03-evidence-and-completion-gates.md`
- 変更差分をreviewする場合: `docs/ai-governance/16-change-scoped-interface-review.md`
- 変更内容に直接関係する詳細文書だけ:
  - 認知・初見理解: `04-cognitive-psychology-principles.md`
  - accessibility: `05-accessibility-and-inclusive-design.md`
  - 視覚階層・情報設計: `06-visual-hierarchy-and-information-architecture.md`
  - copy: `07-ui-copy-and-microcopy.md`
  - 状態・回復: `08-state-design-and-error-recovery.md`
  - ユーザー価値: `10-utility-user-goal-and-product-fit.md`
  - 熟練者効率: `11-efficiency-and-expert-use.md`
  - 満足感・信頼感: `12-satisfaction-trust-and-emotional-ux.md`
  - layout、typography、color、theme、icon、motion、視覚的仕上げ: `15-interface-engineering-quality.md`

indexや全詳細文書を機械的に読み直さず、変更範囲から必要な正本を選びます。

## 3. Scope確定

変更差分を対象にする場合は、実装や評価より先に次を行います。

1. target、base ref / SHA、head ref / SHA、commit数、未commit差分を確定する。
2. lockfile、generated、snapshot、vendor、binary等を除外し、除外理由を記録する。
3. 変更fileから直接consumerへ展開し、shared primitiveやglobal tokenでは代表surfaceを追加する。
4. diffの追加側と削除側を読み、Issue、PR本文、commit messageから変更意図を確認する。
5. findingへIntroduced / Regression / Pre-existingを付ける。Pre-existingは今回の判定から分離する。

差分が存在しない場合は直前commitを勝手にreviewせず、確認したrepository状態と選択肢を示します。reviewだけの依頼ではworking treeを変更しません。

## 4. 実行

1. 対象ユーザー、目的、主要task、変更画面、影響stateを特定する。
2. 初見ユーザーが画面目的、現在地、最初の行動、結果、回復方法を判断できるか確認する。
3. 該当するstate matrixを作る。対象外のstateは理由を記す。
4. keyboard、focus、accessible name、semantic structure、contrast、target size、文字拡大、reflow、motion preferenceを確認する。
5. 視覚的優先度、grouping、主操作、長文・大量data・狭幅・RTLを確認する。
6. typography、color / theme、icon、motion、hover / focus / active / disabled / loading等の実装品質を確認する。
7. copyが対象、結果、原因、影響、次の行動を示し、ユーザーを責めないことを確認する。
8. 反復操作の手数、入力保持、再選択、shortcut、一括操作、毎回の説明を確認する。
9. 待機、成功、失敗、危険操作、保存、送信、削除、権限の信頼感を確認する。
10. 実装を落とす立場で反証reviewし、P0/P1/P2、回帰、未完成state、証跡不足を探す。
11. 実行した検証、未実行検証、残るriskを記録する。

## 5. Finding

findingはroot cause単位に統合し、次を含めます。

- P0 / P1 / P2
- domain
- Introduced / Regression（変更差分review時）
- `path:line`、screen、component、state
- 現在の実装・描画・操作
- 修正後に成立すべき状態
- 利用者影響
- base/head差分、test、DOM / accessibility tree、screenshot、manual result等の証跡

sourceだけで確定できないvisual/runtime claimは描画確認するか、Not verifiedと記録します。同じ問題を複数domainから重複報告しません。

## 6. 証跡

アプリ本体UIでは [`docs/ai-governance/03-evidence-and-completion-gates.md`](../../../docs/ai-governance/03-evidence-and-completion-gates.md) に従い、該当画面・stateの前後screenshot、test、手動確認、state matrix、domain review、変更scopeを残します。

前後screenshotを取得できない場合は、取得不能理由、代替証跡、残るrisk、次に必要な確認を示し、取得必須の変更を完了扱いにしません。

GitHub共同作業面だけの場合は、差分、Markdown / form構造、link、公開安全性、未実行項目を証跡とします。GitHubが所有する未変更のfocusやplatform stateまで検査対象に広げません。

## 7. 完了

- P0が残る場合は完了不可。
- P1は原則として同じ変更内で修正し、分離する場合は理由と追跡先を示す。
- P2は完了を止めないが、対応しない理由または後続先を記録する。
- 変更差分reviewのPass / FailはIntroducedとRegressionを対象とし、Pre-existingを混ぜない。
- screenshot、test、ユーザーフィードバック、accessibility結果、contrast測定、描画確認を捏造しない。
- governance自体を変更した場合は、`bash scripts/verify-ui-quality-governance.sh`、`bash scripts/verify-agent-harness.sh`、`bash scripts/verify-ai-governance.sh`を実行する。
