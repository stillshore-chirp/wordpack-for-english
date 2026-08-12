# 証跡と完了ゲート

この文書は、アプリ本体UIとGitHub共同作業面を区別し、変更を完了扱いするための証跡と判定条件を定義します。変更差分reviewでは、今回の変更が何を追加・削除し、どのsurfaceへ影響し、どの問題を新規作成または回帰させたかをbase / headの証跡で分離します。

## 1. 対象面

最初に `02-uiux-review-framework.md` で対象面とreview種類を分類します。

| 対象面 | 必要な証跡 |
|---|---|
| アプリ本体UI | 画面・state・操作・accessibility・実装品質・前後差分を含むUI/UX証跡 |
| GitHub共同作業面 | repositoryが制御する文言、項目、順序、必須性、Markdown、link、公開安全性 |
| 混在 | 両方を別々に満たす |
| N/A | UIまたはGitHub共同作業面を変更しない理由を短く示す |

表示場所だけで分類しません。GitHub PagesやGitHub App等、repositoryが独自のlayout、操作、stateを実装する場合はアプリ本体UIです。

## 2. 変更scopeの証跡

未commit差分、branch、commit range、Pull Requestをreviewする場合は、`16-change-scoped-interface-review.md`に従い次を残します。

- target種別。
- base ref / SHA、head ref / SHA。
- 対象commit数、staged / unstaged差分。
- files in scope。
- lockfile、generated、snapshot、vendor、binary等の除外と理由。
- changed fileから追加確認したroute、parent、consumer、representative surface。
- 未確認consumerと境界。
- Issue、PR本文、commit message、受け入れ条件から確認した変更意図。
- diffの追加側と削除側を確認した記録。

scopeを確定できない場合は、変更起因のfindingや全体coverageを断定しません。差分がない時に直前commitへ勝手に切り替えません。

## 3. アプリ本体UIの証跡

変更に該当する範囲で、次を残します。

- 対象ユーザー、利用文脈、目的、支援するtask / decision / feedback / recovery。
- 変更されたscreen、component、state、入力、出力。
- 初見simulationと認知負荷確認。
- state matrix。
- accessibility確認。
- 視覚階層と情報設計。
- layout、adaptation、RTL、safe area。
- typography、font、wrap、truncation、dynamic value。
- color / theme、semantic token、contrast pair、appearance。
- icon、interaction state、motion、reduced motion、visual finish。
- copyと用語。
- 熟練者効率。
- 満足感・信頼感。
- 反証review。
- 実行したtest、測定、手動確認。
- 実行していない検証、その理由、残risk、次に必要な確認。

確認対象がないdomainは`Pass`または`Clear`とせず、「変更差分に確認対象なし」と記録します。確認したがfindingがない場合だけ`Clear`とします。

### 前後screenshot

アプリ本体UIまたはrepositoryが制御する独自UIの変更では、該当screen・stateの変更前と変更後のscreenshotをPR本文へ添付します。

少なくとも次を満たします。

- 同じviewport、theme、data / state、zoom条件で比較できる。
- happy pathだけでなく、今回影響するempty、error、disabled、narrow、long-content等を含む。
- screenshotがsourceやtestの主張と同じheadを示す。
- secret、個人情報、本番data、追跡可能な識別子を含まない。

取得できない場合は、次を示します。

- 取得できなかったscreen / state / viewport。
- 理由。
- 代替証跡。
- 残risk。
- 次に必要な確認。

受け入れ条件または変更内容上screenshotが必須なのに取得できない場合は、完了扱いにしません。

### 描画・操作・測定

sourceだけで確定できないclaimには、次のうち必要な証跡を付けます。

- browserでの描画結果。
- DOM / accessibility tree。
- keyboard traversal、focus移動・復帰。
- screen reader操作。
- 320 CSS px、200% zoom、文字拡大、長文、大量data。
- light / dark / forced colors / reduced motion / RTL。
- foreground / backgroundのcontrast測定。
- font request、fallback、weight、wrap、layout shift。
- animation、performance、visual regression。

実行していない場合はNot verifiedとし、確認済みへ変換しません。

## 4. Findingの証跡

各findingはroot cause単位で次を持ちます。

| 項目 | 内容 |
|---|---|
| Priority | P0 / P1 / P2 |
| Domain | 所有する詳細正本 |
| Change status | Introduced / Regression（変更差分review時） |
| Location | `path:line`、screen、component、state |
| Current | 現在の実装・描画・操作 |
| Expected | 修正後に成立すべき状態 |
| User impact | 理解、操作、回復、効率、信頼への影響 |
| Evidence | diff、base側、test、DOM、accessibility tree、screenshot、manual result、測定 |

同じroot causeを複数domain、複数componentから重複報告せず、影響箇所を一件へまとめます。

### Introduced

今回の変更が新しい問題を作ったことをhead側とdiffで確認します。

### Regression

base側では成立していたqualityが、今回の変更で弱くなったことをbase / headの比較で確認します。削除行のsignalだけで断定せず、等価な代替がないことと利用者影響を確認します。

### Pre-existing

base側でも同じ問題が存在し、今回の変更が作成・弱体化していないことを確認します。今回のfinding件数、P0/P1/P2判定、完了可否から分離し、必要なら別Issueへ接続します。

## 5. GitHub共同作業面の証跡

Issue / PR template、repository Markdown、workflowの入力・説明等では、次を確認します。

- 変更した文言、項目、順序、必須性、設定の差分。
- Markdown、form、YAML、frontmatter等の構造。
- link、command、移動先file。
- 公開安全性。
- previewまたは実page確認が必要か。
- 実行していない検証と残risk。

GitHubが所有し、repositoryが変更していないlayout、keyboard、focus、loading、permission stateへ、アプリ本体UIと同じstate matrixやaccessibility証跡を要求しません。screenshotは、repositoryが制御する視覚構成・操作が実質的に変わる場合、受け入れ条件に含まれる場合、または明示依頼がある場合に必要です。

## 6. 完了ゲート

### 共通

- 依頼の成果と受け入れ条件を満たす。
- target、scope、coverage、除外、未確認範囲が分かる。
- P0が残っていない。
- P1を修正したか、分離理由と追跡先を示している。
- 対象面に対応する証跡がある。
- 実行した検証と観察結果を示す。
- 未実行検証、その理由、残risk、次に必要な確認を示す。
- 実施していない確認を成功扱いしていない。
- 公開物の安全性を確認している。

### アプリ本体UI

- ユーザー価値と主要taskを説明できる。
- 初見理解と該当state matrixを確認している。
- accessibility、視覚階層、copy、熟練者効率、信頼感を確認している。
- 変更に関係するlayout、typography、color / theme、icon、motion、interaction stateを確認している。
- sourceだけで確定できないvisual / runtime claimを描画・操作・測定で確認したか、Not verifiedとしている。
- 反証reviewを実施している。
- 必要な前後screenshotをPRで確認できる。

### 変更差分review

- base / headと変更意図が確定している。
- changed fileから影響surfaceへ展開している。
- diffの追加側と削除側を確認している。
- IntroducedとRegressionを今回の判定対象にしている。
- Pre-existingを今回の責任とverdictから分離している。
- 未確認consumerをreview済みと表現していない。

### Pull Request

PRをマージ可能な状態として報告する場合は、次を満たします。

- latest headについて、対象branchで定義されたpush / pull_request等のCIが成功している。
- latest meaningful changeに対するGitHub上で確認可能な自動または人間のcode reviewがcleanである。
- actionableな未解決review threadがない。
- GitHubのmergeabilityがcleanで、conflictやblocking conditionがない。

source変更でcode reviewが提供されない場合、代替自己reviewは補助証跡に限り、マージ可能状態の代替にしません。同じheadでclean reviewを複数回集める必要はありません。指摘対応でheadが変わった場合だけ、CIと該当reviewを再確認します。mergeまたはcloseは別の明示指示がある場合だけ行います。

## 7. 推奨検証

環境と変更範囲に応じて選びます。

- lint、format、typecheck。
- Unit / Integration / contract test。
- E2E / Storybook / Playwright。
- axe-core等の自動accessibility検査。
- keyboard、accessibility tree、screen reader。
- screenshot / visual diff。
- responsive、320 CSS px、200% zoom、text resize、content stress。
- RTL、light / dark、forced colors、reduced motion。
- contrast、font loading、layout shift、animation、performance。
- Markdown / YAML / frontmatter / link検査。
- governance変更では `scripts/verify-ui-quality-governance.sh`、`scripts/verify-agent-harness.sh`、`scripts/verify-ai-governance.sh`。

利用できない検証は、存在しない成果物として捏造せず、理由と残riskを報告します。

## 8. 報告

`templates/completion-gate-report.md`を使うか、同等の情報をPR本文へ記録します。空の項目を定型的なN/Aで埋めるより、今回のscope、確認済みdomain、未確認範囲、変更分類が明確な報告を優先します。
