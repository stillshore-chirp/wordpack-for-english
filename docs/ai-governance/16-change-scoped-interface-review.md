# 変更差分に対するインターフェースレビュー

この文書は、未commit差分、作業branch、commit range、Pull Requestに対して、今回の変更がUI/UXへ与える影響を特定する手順の正本です。repository全体のUI監査とは分け、変更で新たに生じた問題、既存挙動を弱めた回帰、変更前から存在した問題を混同しません。

## 1. レビュー対象を確定する

レビューを始める前に、target、base、headを明示します。

- Pull Request: PRのbase refとhead refを使う。
- branch: default branchとのmerge-baseをbase、現在のHEADをheadとする。
- commit range: ユーザーが指定したrangeをそのまま使う。
- working tree: stagedとunstagedを区別し、branchがdefault branchより進んでいる場合は、そのcommit差分と未commit差分の両方を対象にする。

対象指定がなく、branchにcommit差分も未commit差分もない場合は、任意の直前commitへ勝手に切り替えません。確認できたrepository状態を示し、直前commit、指定range、repository全体監査のどれを行うか確認します。

## 2. Scope block

レビュー冒頭に少なくとも次を残します。

| 項目 | 内容 |
|---|---|
| Target | working tree / branch / range / PR番号 |
| Base | refとcommit SHA |
| Head | refとcommit SHA |
| Commit | 対象commit数と未commit差分の有無 |
| Files | 除外後の対象file数 |
| Excluded | lockfile、generated、snapshot、vendor、binary等と除外理由 |
| Expanded surfaces | 変更fileから追加確認した画面・component・consumer |
| Intent | Issue、PR本文、commit messageから確認した目的・受け入れ条件 |

base/headを取得できない場合は、比較不能な範囲と理由を明示し、変更起因の断定をしません。

## 3. Fileではなく利用者面へ展開する

変更fileは証拠の入口であり、レビュー対象そのものとは限りません。

- page / component変更では、そのcomponentを直接描画するroute、parent、story、testを確認する。
- shared component、design token、theme、spacing、typography、icon、utilityの変更では、代表的なconsumerへ展開する。
- backendやschemaの変更でも、loading、empty、partial、error、permission、copy、recoveryが変わる場合はUI面へ展開する。
- translation catalogue、content model、feature flagの変更では、表示されるstateとfallbackを確認する。

通常は直接consumerまでを確認します。shared primitiveやglobal tokenは二段先まで影響し得るため、代表surfaceを追加します。際限なく全repositoryへ広げず、確認したconsumer数と未確認数を記録します。

## 4. 追加行と削除行を読む

最終状態だけでは回帰を見落とすため、diffの`+`側と`-`側を同じ重さで確認します。

削除側では、次のsignalが代替なしに失われていないかを確認します。

- accessible name、label、semantic element、role、state、description。
- `focus-visible`、focus移動・復帰、keyboard handler、Escape等の操作。
- loading、empty、error、disabled、permission、retry、undo、confirmation。
- status message、live region、error association。
- responsive rule、wrap、overflow、safe area、RTL対応。
- contrast token、focus token、theme variant、reduced motion。
- user-facing copy、対象範囲、結果、回復方法、危険性の説明。
- input保持、再試行、一括操作、shortcut、熟練者向けの近道。

削除されたsignalが別の実装へ等価に置き換えられている場合は問題にしません。signalは調査の入口であり、利用者影響と描画・操作の証拠が確認できた時だけfindingにします。

## 5. Findingの変更分類

各findingへ次のいずれかを付けます。

### Introduced

今回の変更が、新しい問題を作った場合です。

- 追加されたicon-only controlにaccessible nameがない。
- 新しいstateだけ狭幅で操作不能になる。
- 追加copyが対象や結果を誤解させる。

### Regression

変更前は成立していた品質が、今回の変更で弱くなった場合です。

- focus indicator、error recovery、input保持が削除された。
- 既存のresponsive挙動が崩れた。
- 明確だったlabelやscopeが曖昧になった。

回帰判定はbase側のsource、test、screenshot、描画結果で確認します。近くにあるだけの既存問題を回帰として扱いません。

### Pre-existing

対象surfaceには存在するが、今回の変更が作っても弱めてもいない問題です。

- 変更file内でも、差分が触れていない既存実装に起因する。
- base側で同じ問題が再現する。

pre-existingは今回の変更責任と分けて報告し、原則として今回のPass/Fail判定へ含めません。ただし、今回の目的達成や安全なreleaseを不可能にする場合は、別Issue化またはscope変更の判断を明示します。

## 6. 変更意図と未完成状態

Issue、PR本文、受け入れ条件、commit messageを読み、実装が宣言した結果を満たすか確認します。

- 新しいvariant、theme、size、stateがhover / focus / active / selected / disabled / loadingまで揃っているか。
- 新しいcomponentが通常状態だけでなく、empty、error、narrow、long-contentへ対応しているか。
- 新しいuser-facing textが既存のlocalization方式と用語へ接続されているか。
- 兄弟surfaceへ同じ操作や情報が必要なのに、一部だけ変更されていないか。
- 変更後のUserManual、test、story、screenshot、state matrixが実装と一致するか。

Issueに書かれていない追加要求をscope creepとして押し付けません。目的達成に不可欠な欠落と、別の改善機会を区別します。

## 7. Domain review

Scope確定後、変更で証拠がある領域だけを詳細正本へrouteします。

- ユーザー価値・目的適合: `10-utility-user-goal-and-product-fit.md`
- 初見理解・認知負荷: `04-cognitive-psychology-principles.md`
- 状態・回復: `08-state-design-and-error-recovery.md`
- accessibility: `05-accessibility-and-inclusive-design.md`
- 視覚階層・情報設計: `06-visual-hierarchy-and-information-architecture.md`
- copy: `07-ui-copy-and-microcopy.md`
- layout、typography、color、motion、visual finish: `15-interface-engineering-quality.md`
- 熟練者効率: `11-efficiency-and-expert-use.md`
- 信頼感: `12-satisfaction-trust-and-emotional-ux.md`

変更に証拠がない領域を形式的にPassとせず、「変更差分に確認対象なし」と記録します。

## 8. Severityと判定

P0/P1/P2は`02-uiux-review-framework.md`と各詳細正本に従います。変更差分レビューの判定対象は、原則としてIntroducedとRegressionです。

- P0が残る: Fail。完了不可。
- P1が残る: 原則Fail。同じ変更内で修正するか、分離理由と追跡先を示す。
- P2だけ残る: Pass可。対応しない理由または後続先を記録する。
- actionable findingなし: 必要なverificationが完了している場合だけPass。

Pre-existingは別表に最大限要点を絞って記録し、今回のfinding件数や判定を水増ししません。

## 9. Evidence

各findingは次を持ちます。

| 項目 | 内容 |
|---|---|
| Priority | P0 / P1 / P2 |
| Domain | 所有する詳細正本 |
| Change status | Introduced / Regression |
| Location | file:line、screen、component、state |
| Current | 現在の実装・描画・操作 |
| Expected | 修正後に成立すべき状態 |
| User impact | 理解、操作、回復、効率、信頼への影響 |
| Evidence | base/head差分、test、DOM、accessibility tree、screenshot、manual result |

同じroot causeは一件へ統合し、影響箇所を列挙します。sourceだけで確定できないvisual/runtime claimは描画確認するか、Not verifiedと明記します。

## 10. Read-only review

レビューだけを依頼された場合はworking treeを変更しません。

- PR refはfetchして比較し、作業中のfileをcheckout、stash、switchで書き換えない。
- 描画確認で別refを起動する必要がある場合は、一時worktree等の隔離環境を使う。
- 実装も依頼された場合は、findingを変更scopeとして修正し、同じbase/head条件で再reviewする。

## 11. Review output

`templates/uiux-review-report.md`へ次を残します。

1. Scope blockと変更意図。
2. 領域別coverageと未確認範囲。
3. Introduced / Regression findings。
4. 今回の責任外であるPre-existing findings。
5. 検討したがfindingにしなかった候補と理由。
6. 実行したcommand、描画・操作確認、結果。
7. 未実行検証、理由、残リスク。
8. Pass / FailとP0/P1/P2。
