# AIエージェントレビュー・プロトコル

この文書は、AIエージェントがUI/UXレビューを実行する時の手順を定義します。AIに「良さそう」と判断させるのではなく、scope確定、観察、判定、反証、証跡提出を強制します。

## 1. Reviewの種類

最初にreviewの種類を決めます。

- **変更差分review**: 未commit差分、branch、commit range、Pull Requestが対象。`16-change-scoped-interface-review.md`を適用する。
- **screen / flow review**: 指定された画面、component、feature、flowが対象。対象stateとviewportを明示する。
- **repository監査**: repositoryが制御するUI全体が対象。変更起因の分類は行わず、監査境界と未確認surfaceを示す。

変更差分reviewでは、base / head、追加・削除差分、影響surface、変更意図を確定してからdomain reviewを始めます。

## 2. 推奨ロール

一つのエージェントが実行する場合でも、次のロールを分けてください。

### 2.1 Scope評価者

対象ref、merge-base、未commit差分、除外file、影響surface、Issue / PRの変更意図を確定します。review-onlyではworking treeを変更しません。

### 2.2 実装者

要件を実装します。ただし、自分の実装を最終承認してはいけません。

### 2.3 価値評価者

対象ユーザー、目的、支援するtask、意思決定への貢献を確認します。

### 2.4 初見ユーザー

画面を初めて見た前提で、目的、現在地、最初の行動、結果予測、回復手段を確認します。

### 2.5 認知負荷監査者

記憶要求、選択肢過多、内部用語、過剰説明、判断負荷を確認します。

### 2.6 Accessibility監査者

native semantics、keyboard、focus表示・移動・復帰、name / role / state、form、live region、zoom / reflow、forced colors、reduced motionを確認します。

### 2.7 視覚階層・情報設計批評者

重要度と見え方の一致、主操作、情報密度、余白、grouping、scan性、navigation構造を確認します。

### 2.8 インターフェース実装品質監査者

layout、adaptation、RTL、typography、color / theme、icon、motion、各interaction state、visual finishを確認します。

### 2.9 状態設計監査者

通常state以外を確認し、stateごとの理解、次action、recovery、通知を確認します。

### 2.10 Copy監査者

用語、button / link、error、empty state、toggle、localization、toneを確認します。

### 2.11 熟練者評価者

反復作業の手数、再入力、確認の過剰さ、shortcut、一括操作、復帰性を確認します。

### 2.12 信頼感評価者

待機、成功、失敗、危険操作、権限、個人情報、削除、送信、公開の安心感を確認します。

### 2.13 反証reviewer

実装を落とすつもりで、P0、Regression、未完成state、証跡不足を探します。

### 2.14 検証報告者

実行した検証、実行していない検証、残riskを分離します。

## 3. 実行順序

```txt
review種類の確定
↓
base / head・変更意図・除外fileの確定
↓
変更fileから影響surfaceへ展開
↓
diffの追加側・削除側を確認
↓
ユーザー価値評価
↓
初見simulation
↓
state matrix
↓
認知負荷確認
↓
accessibility確認
↓
視覚階層・情報設計確認
↓
layout・typography・color / theme・icon・motion確認
↓
copy確認
↓
熟練者効率確認
↓
満足感・信頼感確認
↓
findingをIntroduced / Regression / Pre-existingへ分類
↓
反証review
↓
証跡・未実行検証・verdictの報告
```

screen / flow reviewとrepository監査では、base / headと変更分類を対象境界・coverageの記録へ置き換えます。

## 4. Scopeとcoverage

- 変更fileだけでcoverageを主張せず、直接consumerと代表surfaceを確認する。
- shared primitive、global token、themeは複数surfaceへ届くため、影響範囲を追加確認する。
- 確認したsurface数、未確認consumer、対象外stateを明示する。
- 証拠がないdomainを`Pass`または`Clear`とせず、「変更差分に確認対象なし」または`Not verified`とする。
- repository全体を確認していないのに、全体監査済みと表現しない。

## 5. Findingの所有と統合

- 一つのroot causeは一件のfindingとし、影響箇所を列挙する。
- 同じ問題をaccessibility、layout、copy等から重複報告せず、根本規則を所有する正本へ割り当てる。
- findingにはpriority、domain、location、current、expected、user impact、evidenceを含める。
- 変更差分reviewではIntroducedまたはRegressionを付ける。Pre-existingは今回の責任とverdictから分離する。
- sourceだけで確定できないvisual / runtime claimは描画確認するか、Not verifiedとする。

## 6. 反証reviewのルール

反証reviewでは、次の態度を取ります。

- 実装を褒める前に、完了不可理由を探す。
- diffの追加側だけでなく、削除されたquality signalを探す。
- 通常state以外を重点的に見る。
- screenshotがhappy pathだけではないか疑う。
- shared token / primitiveの変更が未確認surfaceへ届いていないか疑う。
- 新しいvariant、theme、size、copy、componentが一部stateだけ未完成ではないか疑う。
- 自動検査で検出できない使いにくさを探す。
- 初心者向け配慮が熟練者効率を壊していないか疑う。
- ユーザーに不安や責任転嫁を与えていないか疑う。
- 証跡が実際の確認を示しているか疑う。
- base側で同じ問題が再現する場合、今回のRegressionとして誤報していないか疑う。

## 7. Read-only境界

reviewだけを依頼された場合はsourceを変更しません。

- PRや別branchを確認するために、作業中のtreeをcheckout、switch、stashで書き換えない。
- refをfetchし、diffとblobを直接読む。描画が必要なら一時worktree等の隔離環境を使う。
- 実装も依頼された場合は、findingを変更scopeとして修正し、最新headで同じreviewを再実行する。

## 8. 出力の制約

禁止:

- 「問題ありません」とだけ報告する。
- 検証していないことを確認済みにする。
- 実ユーザーから得ていない反応を、ユーザー事実のように書く。
- 理論名だけを並べて指摘にしない。
- P0をP1やP2に格下げする。
- Pre-existingを今回の変更findingへ混ぜる。
- uninspected surfaceをreview済みと表現する。
- sourceだけからcontrast、wrap、motion、runtime behaviorを断定する。

必須:

- target、scope、coverage、除外、未確認範囲を明示する。
- Pass / Failを明示する。
- P0/P1/P2を分ける。
- 変更差分reviewではIntroduced / Regression / Pre-existingを分ける。
- evidenceを示す。
- 実行commandと観察結果を示す。
- 未実行検証と残riskを示す。

## 9. AIレビューの限界

AIによる初見simulation、copy評価、visual critiqueは、実ユーザーテストや専門支援技術検証そのものではありません。

- 実ユーザーの反応、task完了率、満足度を観測していない場合は仮説として扱う。
- screen reader、browser、device、font rendering等を実行していない場合は未確認とする。
- AIが判断しやすい規則準拠と、実利用でしか分からない価値・迷い・performanceを分ける。
- 重大な仮説は、後続のuser test、計測、実機確認へ接続する。
