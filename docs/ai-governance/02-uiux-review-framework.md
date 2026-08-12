# UI/UXレビュー・フレームワーク

この文書は、AIエージェントがUI/UXをレビューするための中心規約です。画面の見た目だけでなく、ユーザー価値、理解、state、回復、accessibility、実装品質、反復利用、信頼感、および今回の変更が既存品質へ与えた影響を扱います。

## 1. 適用対象と所有境界

証跡の範囲は、表示場所ではなく、変更対象のUIと操作を誰が制御しているかで決めます。

| 対象面 | 例 | リポジトリが制御するもの | 適用するレビュー |
|---|---|---|---|
| アプリ本体UI | Web / desktop app、製品site、GitHub Pages上の製品画面 | layout、操作、state、focus、accessibility、copy、theme、motion | 本文書の全review経路とアプリUI証跡 |
| GitHub共同作業面 | Issue / PR template、Issue / PR本文、repository Markdown、workflowの入力・説明 | 文言、項目、順序、必須性、Markdown、設定 | 内容・構造・表示・link・公開安全性の範囲に比例したreview |

browserで表示されること自体は、アプリ本体UIである根拠になりません。GitHub共同作業面では、GitHubが提供していて変更していないlayout、keyboard操作、focus、loading stateまでrepository変更の検証対象に広げません。一方、GitHub Pages、GitHub App、埋め込みWeb UIなど、repository側が独自UIを実装する場合はアプリ本体UIとして扱います。

GitHub共同作業面だけの変更でも、repositoryが制御するcopyの明確さ、入力順、必須項目、送信前に必要な判断材料、Markdownの崩れ、link、公開安全性は確認します。対象面が混在する変更は、それぞれ別に判定し、一方の証跡で他方を代用しません。

## 2. Reviewの種類

### 変更差分review

未commit差分、作業branch、commit range、Pull Requestを対象とします。`16-change-scoped-interface-review.md`でbase / head、除外file、追加・削除差分、影響surface、変更意図を確定し、findingをIntroduced / Regression / Pre-existingへ分類します。

### Screen / flow review

ユーザーが指定したscreen、component、feature、flowを対象とします。対象state、viewport、theme、user path、除外範囲を明示します。

### Repository監査

repositoryが制御するUI全体または大きな領域を対象とします。確認できるcomplete flowへ境界を絞り、未確認surfaceを示します。変更起因の分類は行いません。

review種類を曖昧にしたまま、「全体を確認した」「変更に問題がない」と報告しません。

## 3. UI/UX品質の定義

このガバナンスでは、良いUI/UXを次のように定義します。

> 対象ユーザーが、特定の文脈で、目的を達成できること。
> その過程が分かりやすく、見やすく、操作しやすく、失敗しても回復でき、環境の違いに適応し、慣れれば速く、安心して使えること。

したがって、UI/UX reviewは次を同時に扱います。

- ユーザー価値: そもそも役に立つか。
- 初見理解: 初めて見ても画面目的、現在地、最初の行動が分かるか。
- 認知負荷: 覚えさせすぎず、判断させすぎないか。
- 視覚階層・情報設計: 重要度、grouping、navigationが理解を助けるか。
- 状態理解・回復: loading、empty、error、disabled、permission等で次の行動が分かるか。
- Accessibility: 多様な利用者・入力方法・表示環境で使えるか。
- インターフェース実装品質: layout、typography、color / theme、icon、motion、interaction stateが安定しているか。
- Copy: 対象、結果、原因、影響、回復がユーザーの言葉で伝わるか。
- 熟練者効率: 反復利用で不要な手数・再入力・説明に妨げられないか。
- 満足感・信頼感: 結果、危険性、dataの扱いが誠実で安心できるか。
- 変更完全性: 宣言したvariant、state、sibling surface、test、documentationまで揃っているか。

## 4. Reviewの基本質問

アプリ本体UIと、repositoryが独自に制御するUIでは、次に答えます。GitHub共同作業面だけの変更では、repositoryが制御する文言・構造に該当する質問だけを適用します。

1. これは誰のためのUIか。
2. そのユーザーはどの文脈で何を達成したいか。
3. このUIは何を理解・判断・実行・回復しやすくするか。
4. 初見で何の画面か、今どこか、最初に何をすべきか分かるか。
5. 操作したら何が起きるか、どの対象へ作用するか予測できるか。
6. 待機、空、失敗、無効、権限不足、部分dataで次の行動が分かるか。
7. keyboard、支援技術、狭幅、拡大、forced colors、reduced motionで主要taskを完了できるか。
8. hierarchy、layout、typography、color、icon、motionが内容とstateを正しく支えるか。
9. copyは対象、結果、原因、影響、回復を示すか。
10. 慣れたユーザーが不要に遅くならないか。
11. ユーザーに不必要な不安、恥、責任転嫁、混乱を与えないか。
12. 今回の変更で、以前成立していたquality signalを削除・弱体化していないか。
13. 確認した範囲と未確認範囲を証跡で説明できるか。

## 5. Review pipeline

### 5.1 Scope・変更意図

変更差分reviewでは最初に次を確定します。

- target、base ref / SHA、head ref / SHA。
- commit数、staged / unstaged差分。
- lockfile、generated、snapshot、vendor、binary等の除外。
- changed fileが描画・利用されるroute、parent、consumer、representative surface。
- Issue、PR本文、commit message、受け入れ条件。
- diffの追加側と削除側。

差分がない場合は任意の直前commitへ切り替えません。repository状態を示し、review対象を確認します。

### 5.2 目的・価値

- 対象ユーザーと利用文脈を特定する。
- ユーザー目的を結果で記述する。
- UIが支援するtask、decision、feedback、recoveryを明確にする。
- UIがなくても困らない場合、存在理由を再検討する。
- 判断に使われない情報、重複する操作、内部都合の表示を削る。

### 5.3 初見理解・認知負荷

3秒だけ見た前提で、次を判断します。

- 何の画面か。
- 今どこか。
- 何が重要か。
- 最初に何をすべきか。
- 操作結果と適用範囲を予測できるか。

さらに、必要条件、選択中state、過去入力を画面へ出し、不要な記憶、内部用語、選択肢過多、説明過多を避けます。

### 5.4 State設計

アプリ本体UIでは通常stateだけで判断せず、該当するstate matrixを作成または更新します。対象外stateには理由を書きます。

- 通常
- loading
- 初回empty
- no-results / filter-empty
- partial data
- error
- validation error
- disabled / unavailable
- permission denied
- offline / maintenance
- success
- narrow width
- 200% zoom / text resize
- long content / large data
- dark / alternate appearance
- reduced motion / forced colors（関係する場合）

各stateで、ユーザーが見るもの、理解できること、次action、recovery、a11y通知、証跡、判定を記録します。

### 5.5 Accessibility

`05-accessibility-and-inclusive-design.md`を正本として確認します。

- native semantics。
- keyboard pathと採用widget pattern。
- focus表示、移動、trap、復帰。
- accessible name、role、state、value。
- form label、constraint、error association、input保持。
- live region、status、notification duration。
- heading、landmark、list、table、image、media。
- contrast、forced colors、target size。
- 320 CSS px、200% zoom、text resize、safe area。
- `prefers-reduced-motion`、autoplay、time limit。

自動検査だけで合格とせず、keyboard、accessibility tree、描画、必要な支援技術で確認します。

### 5.6 視覚階層・情報設計

- 一番重要な情報と主操作が自然に見つかるか。
- 補助情報、副操作、危険操作が競合していないか。
- grouping、余白、整列、densityが構造を伝えるか。
- 検索、tab、filter、件数、selectionのscopeが明確か。
- navigation階層、現在地、戻り先がユーザーのmental modelと一致するか。
- screenをscanした時、heading、label、state、warningから必要情報へ到達できるか。

### 5.7 インターフェース実装品質

`15-interface-engineering-quality.md`を正本として、変更に関係する領域を確認します。

- framework、styling方式、component library、design tokenのrecon。
- content-driven breakpoint、container query、safe area、RTL、logical property。
- font load / fallback、type scale、line-height、measure、wrap、truncation、tabular numbers、mobile input。
- semantic color token、実描画pairのcontrast、light / dark / increased contrast、gamut / fallback。
- icon family、stroke、optical alignment、radius、border、shadow、surface hierarchy。
- hover、focus、active、selected、disabled、loading、success、error。
- interruptible transition、reduced motion、property限定、performance、初回animation。

sourceだけで確定できないclaimは描画確認するかNot verifiedとします。

### 5.8 Copy・用語

- existing voice、用語、localization方式を確認する。
- buttonは結果が分かる動詞、linkは遷移先が分かる文言にする。
- flow内の語彙、capitalization、perspectiveを一貫させる。
- errorは原因、影響、data保持、回復方法を示す。
- empty / no-resultsは現在stateと次actionを示す。
- toggleはON stateを表し、disabledは理由と有効化条件を示す。
- 文字列断片の連結で翻訳不能な文を作らない。
- high-stakesな場面でplayfulな表現、責任転嫁、曖昧な安心を使わない。

### 5.9 熟練者効率

- 主要反復taskの手数、再入力、再選択、確認を数える。
- input保持、前回設定、shortcut、一括操作、再実行、復帰導線を検討する。
- 初回だけ必要な説明が毎回の障害にならないようにする。
- よく使う操作がrare actionより深い階層に隠れないようにする。
- safetyのための確認と、反復利用を妨げる過剰確認を区別する。

### 5.10 満足感・信頼感

- waiting中に処理対象、進行、data保持、代替actionが分かるか。
- success時に完了内容、次action、undo / detailが分かるか。
- failure時に責任転嫁せず、原因、影響、recovery、data保持を示すか。
- 削除、送信、公開、課金、権限、個人情報で対象、件数、影響、取り消し可否を示すか。
- 実際より安全または危険に見せず、誠実なtoneを保つか。

### 5.11 変更完全性

- 新しいvariant、size、themeが各interaction stateへ適用されているか。
- 新しいcomponentがempty、error、disabled、narrow、long-contentへ対応するか。
- 新しいcopyがtranslation catalogue、用語、pluralizationへ接続されるか。
- sibling surface、story、test、UserManual、state matrixの更新が必要か。
- Issueの目的に不可欠な欠落と、別の改善機会を分ける。

### 5.12 反証review

最後に実装を落とすつもりで確認します。

- 目的、scope、最初のactionが曖昧ではないか。
- stateが混ざる、抜ける、recoveryできない箇所はないか。
- 削除側diffでaccessibility、responsive、copy、recovery、efficiencyのsignalを失っていないか。
- shared token / primitiveが未確認surfaceへ波及していないか。
- sourceだけの推測を描画確認済みと扱っていないか。
- 初心者向け配慮が熟練者効率を壊していないか。
- user trust、data safety、公開範囲を誤解させないか。
- evidenceがclaimを支えているか。

## 6. Findingの扱い

一つのroot causeは一件へ統合し、影響箇所を列挙します。同じ問題を複数domainから重複報告しません。

各findingは次を含みます。

- P0 / P1 / P2。
- 所有domain。
- location。
- current implementation / behavior。
- expected state。
- user impact。
- evidence。
- 変更差分reviewではIntroduced / Regression。

Pre-existingは今回の責任、finding cap、Pass / Failから分離します。ただし安全なreleaseやIssue目的達成を妨げる場合は、別Issueまたはscope変更の判断を示します。

## 7. P0 / P1 / P2

### P0: 完了不可

- ユーザー価値、対象ユーザー、支援する目的を説明できない。
- 初見で画面目的、現在地、対象範囲、最初のactionが分からない。
- 主要stateが混ざり、error、permission、empty等を誤認する。
- 原因、影響、recoveryがなく、data lossやtask断念につながる。
- keyboard、focus、name、semantics、contrast、target、zoom / reflow等で主要taskを完了できない。
- stateや意味を色またはmotionだけで伝える。
- 320 CSS pxまたは200%拡大で主要content / controlがclip、overlap、到達不能になる。
- 危険操作、送信、公開、課金、権限、個人情報の対象・影響・取り消し可否が不明。
- 初心者向け導線が主要反復taskを恒常的に妨害する。
- 必須evidenceがない、または未実行検証を成功扱いしている。

### P1: 原則として同じ変更内で修正

- scope、hierarchy、用語、state feedbackが曖昧で理解・効率を明確に損なう。
- wrap、density、theme、icon、motion、responsiveの不整合が複数箇所へ波及する。
- empty、success、errorの次actionが弱い。
- 反復作業の手数、再入力、確認が多いがtaskは完了できる。
- shared token / primitiveの問題が代表surfaceで再現する。

### P2: Issue化可

- taskを妨げない局所的な余白、copy、icon、radius、shadow、transitionの改善。
- 将来的なshortcut、一括操作、polish。
- user research、計測、実機確認が必要な改善仮説。

## 8. 数値基準

- standard、仕様、既存design system、対応環境の契約を優先する。
- 数値は文脈がない場合の最低目安または開始点として使い、数値だけで設計品質を決めない。
- 通常text contrastは4.5:1、大きいtextと必要な非text部品は3:1を最低目安とする。
- 最小targetは24×24 CSS pxまたは適用可能な例外・spacing条件を確認し、touch中心ではより大きくする。
- 200% zoomと320 CSS px相当で主要taskが成立することを確認する。
- body text、line-height、measureは実際のfont、言語、density、contentで判断する。

## 9. AIレビューの限界

AIによる初見simulation、copy評価、visual critiqueは有用ですが、実ユーザーテスト、screen reader test、実機performance testそのものではありません。

- 実ユーザーから得ていない反応を「ユーザーがそう感じた」と書かない。
- user test、screen reader、browser / device確認を実施していなければ明記する。
- AIが見つけやすい規則違反と、実利用でしか分からない価値・迷い・performanceを分ける。
- 重大な仮説は後続の計測、実機確認、user testへ接続する。
