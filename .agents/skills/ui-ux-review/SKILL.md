---
name: ui-ux-review
description: "アプリ本体またはリポジトリが制御する独自UIの変更レビューと既存フロー監査で、ユーザー価値、状態、アクセシビリティ、視覚階層、コピー、熟練者効率、信頼感を証跡付きで確認する。"
---

# UI/UXレビュー Skill

## 1. 発動条件と対象面

次の変更で使います。

- 画面、ページ、コンポーネント、レイアウト、ナビゲーション、フォーム
- 表示文言、ラベル、説明、エラー、通知
- loading、empty、no-results、partial、error、validation-error、disabled、permission-denied
- アクセシビリティ、レスポンシブ、操作方法
- backend変更でも、利用者に見える結果や回復方法が変わるもの
- 既存画面、journey、funnel、設定経路など、単一画面または複数ステップの体験監査

最初に [`docs/ai-governance/02-uiux-review-framework.md`](../../../docs/ai-governance/02-uiux-review-framework.md) で対象面を分類します。

- **アプリ本体UI**: リポジトリがレイアウト、操作、状態、フォーカス、アクセシビリティを実装する画面。本文書の全手順を適用する。
- **GitHub共同作業面**: Issue / PR template、repository Markdown、workflow説明など。リポジトリが制御する文言、構造、表示、リンク、公開安全性だけを範囲に比例して確認する。
- **混在**: 両方を別々に確認し、一方の証跡で他方を代用しない。

## 2. レビュー経路を選ぶ
<!-- agent-harness:uiux-review-routing:start -->

- **UI変更レビュー**: 変更した画面、component、状態、文言、操作を確認する。単一画面の局所変更だけならフロー監査を追加しない。
- **フロー監査**: 既存画面または複数ステップの体験を監査する依頼、または画面遷移を追わなければタスク達成を評価できない場合に使う。
- **併用**: UI変更が複数ステップの主要タスクへ影響する場合、取得可能な変更前フローを基準にし、変更レビュー後に同じタスクの変更後フローを監査する。片方の証跡で他方を代用しない。

GitHub共同作業面では、GitHubが所有する未変更の操作フローを監査対象へ広げず、リポジトリが制御する文言、構造、表示、リンクに経路を限定します。
<!-- agent-harness:uiux-review-routing:end -->

## 3. 読む正本

- 全作業: `AGENTS.md` と変更対象に最も近い `AGENTS.md`
- UI品質・P0/P1/P2: `docs/ai-governance/02-uiux-review-framework.md`
- 証跡・完了条件: `docs/ai-governance/03-evidence-and-completion-gates.md`
- 変更内容に直接関係する詳細文書だけ:
  - 認知・初見理解: `04-cognitive-psychology-principles.md`
  - アクセシビリティ: `05-accessibility-and-inclusive-design.md`
  - 視覚階層: `06-visual-hierarchy-and-information-architecture.md`
  - コピー: `07-ui-copy-and-microcopy.md`
  - 状態・回復: `08-state-design-and-error-recovery.md`
  - ユーザー価値: `10-utility-user-goal-and-product-fit.md`
  - 熟練者効率: `11-efficiency-and-expert-use.md`
  - 満足感・信頼感: `12-satisfaction-trust-and-emotional-ux.md`

indexや全詳細文書を機械的に読み直さず、変更範囲から必要な正本を選びます。

## 4. 実行

### 4.1 共通準備

対象surface、対象ユーザー、ユーザー目的、監査対象タスクを特定します。フロー監査では取得手段、開始状態、完了状態、重要な分岐も操作前に定めます。

### 4.2 UI変更レビュー

1. 対象ユーザー、目的、主要タスク、変更画面、影響状態を特定する。
2. 初見ユーザーが画面目的、現在地、最初の行動、結果、回復方法を判断できるか確認する。
3. 該当するstate matrixを作る。対象外の状態は理由を記す。
4. キーボード、フォーカス、accessible name、semantic structure、contrast、target size、文字拡大を確認する。
5. 視覚的な優先度、グルーピング、主操作、長文・大量データ・狭幅を確認する。
6. コピーが原因、影響、次の行動を示し、ユーザーを責めないことを確認する。
7. 反復操作の手数、入力保持、再選択、shortcut、一括操作、毎回の説明を確認する。
8. 待機、成功、失敗、危険操作、保存、送信、削除、権限の信頼感を確認する。
9. 実装を落とす立場で反証レビューし、P0/P1/P2と証跡不足を探す。
10. 実行した検証、未実行検証、残るリスクを記録する。

### 4.3 フロー監査

1. 開始から完了までの重要なステップと期待する状態遷移を番号付きで定める。
2. 現在の監査実行で実際のフローを順に操作し、各ステップの安定後に画面を取得する。
3. 保存した画像そのものを検査してから採用し、操作中に観測した挙動を該当ステップへ記録する。
4. 各findingをステップ番号または採用画像へ結び付け、既存のP0/P1/P2で判定する。
5. 完走または証跡取得できない重要ステップには具体的なblockerを対応させ、監査できた範囲だけを報告し、完全なフロー監査と扱わない。

重要ステップ、finding、静止画の限界は `02-uiux-review-framework.md`、画像の採否、必要な証跡、blockerと完了判定は `03-evidence-and-completion-gates.md` を正本とします。

### 4.4 併用

併用時の順序は、共通準備、変更前フロー監査、UI変更レビュー、変更後の同一フロー監査です。新規フローなど変更前を取得できない場合は、取得不能な重要ステップごとのblocker、仕様・既存testなどの代替基準、残る比較リスクを示します。

## 5. 証跡

アプリ本体UIでは [`docs/ai-governance/03-evidence-and-completion-gates.md`](../../../docs/ai-governance/03-evidence-and-completion-gates.md) に従い、該当画面・状態の前後screenshot、テスト、手動確認、state matrix、各レビュー結果を残します。

フロー監査の証跡セットと採否は、`03-evidence-and-completion-gates.md` に従います。

前後screenshotを取得できない場合は、取得不能理由、代替証跡、残るリスク、次に必要な確認を示し、取得必須の変更を完了扱いにしません。

GitHub共同作業面だけの場合は、差分、Markdown / form構造、リンク、公開安全性、未実行項目を証跡とします。GitHubが所有する未変更のfocusやplatform stateまで検査対象に広げません。

## 6. 完了

- P0が残る場合は完了不可。
- P1は原則として同じ変更内で修正し、分離する場合は理由と追跡先を示す。
- P2は完了を止めないが、対応しない理由または後続先を記録する。
- フロー監査で必須証跡または具体的なblockerがなく、findingを対応する証跡へ追跡できない場合は完了不可。
- screenshotだけからaccessibilityや未観測の挙動を断定しない。
- screenshot、test、ユーザーフィードバック、アクセシビリティ結果を捏造しない。
