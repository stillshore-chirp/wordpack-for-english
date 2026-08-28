# 証跡と完了ゲート

この文書は、アプリ本体UIとGitHub共同作業面を区別し、変更を完了扱いするための証跡と判定条件を定義します。

## 1. 対象面

最初に `02-uiux-review-framework.md` で分類します。

| 対象面 | 必要な証跡 |
|---|---|
| アプリ本体UI | 画面・状態・操作・アクセシビリティ・前後差分を含むUI/UX証跡 |
| GitHub共同作業面 | リポジトリが制御する文言、項目、順序、必須性、Markdown、リンク、公開安全性 |
| 混在 | 両方を別々に満たす |
| N/A | UIまたはGitHub共同作業面を変更しない理由を短く示す |

表示場所だけで分類しません。GitHub PagesやGitHub Appなど、リポジトリが独自のlayout、操作、状態を実装する場合はアプリ本体UIです。

## 2. アプリ本体UIの証跡

変更に該当する範囲で、次を残します。

- 対象ユーザー、目的、支援するタスク
- 変更された画面、component、状態、入力、出力
- 初見シミュレーション
- state matrix
- accessibility確認
- 視覚階層と情報設計
- copyと用語
- 熟練者効率
- 満足感・信頼感
- 反証レビュー
- 実行したtestと手動確認
- 実行していない検証、その理由、残るリスク

### 前後screenshot

アプリ本体UIまたはリポジトリが制御する独自UIの変更では、該当画面・状態の変更前と変更後のscreenshotをPR本文へ添付します。

取得できない場合は、次を示します。

- 取得できなかった検証
- 理由
- 代替証跡
- 残るリスク
- 次に必要な確認

受け入れ条件または変更内容上screenshotが必須なのに取得できない場合は、完了扱いにしません。

## 3. フロー監査の証跡

既存画面または複数ステップの体験を監査する場合は、対象面に応じた既存証跡へ次を追加します。

- 対象surface、対象ユーザー、ユーザー目的、監査対象タスク、取得手段、開始・完了状態
- 順序付きの重要な各ステップと、そこで行った操作、到達した画面・状態
- 現在の監査実行で取得し、保存後に対象画面・状態として検査済みのscreenshotのファイル名または参照、または取得不能の具体的なblocker
- navigation、focus、loading、validation、error recovery、empty state、motionなど、操作中に観測した挙動と確認手段
- 各findingが参照するステップ番号またはscreenshot、観測事実、ユーザー影響、推奨対応、P0 / P1 / P2、証跡上の限界
- 監査できなかった範囲、その理由、残るリスク、次に必要な確認

誤画面、誤状態、blank、loading中、文脈を隠すcrop、別window、half-rendered状態の画像は証跡へ採用せず、再取得します。以前のscreenshot、trace、cache、生成物は比較資料にできますが、現在の監査実行の証跡を代替しません。screenshotだけではsemantic structure、accessible name、contrast比、focus順序、keyboard完走、支援技術への通知、時間変化や回復挙動を確認済みとせず、別の実行証跡または未確認理由を示します。

フローを完走できない、重要ステップを取得・保存・検査できない、または必要な主張を実行証跡で支えられない場合はblockerです。取得手段・環境のblockerは証跡の状態として製品findingのseverityと分けます。監査できた部分を報告することはできますが、完全なフロー監査として完了扱いにしません。

## 4. GitHub共同作業面の証跡

Issue / PR template、repository Markdown、workflowの入力・説明などでは、次を確認します。

- 変更した文言、項目、順序、必須性、設定の差分
- Markdown、form、YAML、frontmatterなどの構造
- link、command、移動先file
- 公開安全性
- previewまたは実ページ確認が必要か
- 実行していない検証と残るリスク

GitHubが所有し、リポジトリが変更していないlayout、keyboard、focus、loading、permission stateへ、アプリ本体UIと同じstate matrixやaccessibility証跡を要求しません。screenshotは、リポジトリが制御する視覚構成・操作が実質的に変わる場合、受け入れ条件に含まれる場合、または明示依頼がある場合に必要です。

## 5. 完了ゲート

### 共通

- 依頼の成果と受け入れ条件を満たす。
- P0が残っていない。
- 対象面に対応する証跡がある。
- 実行した検証と結果を示す。
- 未実行検証、その理由、残るリスクを示す。
- 実施していない確認を成功扱いしていない。
- 公開物の安全性を確認している。

### アプリ本体UI

- ユーザー価値を説明できる。
- 初見理解と主要状態を確認している。
- accessibility、視覚階層、copy、熟練者効率、信頼感を確認している。
- 反証レビューを実施している。
- 必要な前後screenshotをPRで確認できる。

### フロー監査

- 監査対象タスクの開始・完了状態と重要ステップが特定されている。
- 重要な各ステップに、現在の監査実行で取得・検査済みのscreenshotまたは取得不能の具体的なblockerがある。
- 各findingを該当ステップまたはscreenshotへ追跡できる。
- screenshotで確認できる事実と、別の操作・accessibility証跡が必要な事項を分離している。
- blockerが残る場合、監査できた範囲だけを報告し、完全なフロー監査としていない。

### Pull Request

PRをマージ可能な状態として報告する場合は、次を満たします。

- latest headについて、対象branchで定義されたpush / pull_request等のCIが成功している。
- latest meaningful changeに対するGitHub上で確認可能な自動または人間のコードレビューがcleanである。
- actionableな未解決review threadがない。
- GitHubのmergeabilityがcleanで、conflictやblocking conditionがない。

ソースコード変更でコードレビューが提供されない場合、代替自己レビューは補助証跡に限り、マージ可能状態の代替にしません。同じheadでclean reviewを複数回集める必要はありません。指摘対応でheadが変わった場合だけ、CIと該当reviewを再確認します。mergeまたはcloseは別の明示指示がある場合だけ行います。

## 6. 推奨検証

環境と変更範囲に応じて選びます。

- lint、format、typecheck
- Unit / Integration / contract test
- end-to-end test
- Storybook
- Playwright
- axe-core
- screenshot / visual diff
- keyboard操作
- responsive、文字拡大、content stress
- Markdown / YAML / frontmatter / link検査

利用できない検証は、存在しない成果物として捏造せず、理由と残るリスクを報告します。

## 7. 報告

`templates/completion-gate-report.md` を使うか、同等の情報をPR本文へ記録します。空の項目を定型的なN/Aで埋めるより、今回の対象面と未確認範囲が明確な報告を優先します。
