# 証跡と完了ゲート

この文書は、アプリ本体UIとGitHub共同作業面を区別し、変更を完了扱いするための証跡と判定条件を定義します。UI変更レビューで差分を扱う場合は、比較snapshot、追加・削除、影響coverage、変更意図、findingの由来を既存の証跡へ統合します。

## 1. 対象面

最初に `02-uiux-review-framework.md` で分類します。

| 対象面 | 必要な証跡 |
|---|---|
| アプリ本体UI | 画面・状態・操作・アクセシビリティ・前後差分を含むUI/UX証跡 |
| GitHub共同作業面 | リポジトリが制御する文言、項目、順序、必須性、Markdown、リンク、公開安全性 |
| 混在 | 両方を別々に満たす |
| N/A | UIまたはGitHub共同作業面を変更しない理由を短く示す |

表示場所だけで分類しません。GitHub PagesやGitHub Appなど、リポジトリが独自のlayout、操作、状態を実装する場合はアプリ本体UIです。

## 2. 変更scopeの証跡
<!-- agent-harness:uiux-change-scope-evidence:start -->

差分を伴うUI変更レビューでは、UI品質を判定する前に、比較対象と影響範囲を次の記録へ固定します。これはUI影響を確認するための証跡であり、GitHub配送一般の完了条件を定義するものではありません。

| 項目 | 記録 |
|---|---|
| Target snapshot / ref | working tree、commit range、branch、PR等のレビュー対象と識別子 |
| Base ref / SHA、Head ref / SHA | 比較に使ったbaseとhead |
| Commit / diff | 対象commit数、staged / unstaged、追加側・削除側 |
| Diff identifier | `staged=<patch hash|empty>; unstaged=<patch hash|empty>; paths=<sorted changed path set>`。使用したhash方式と取得時点も記録 |
| Intent | Issue、PR本文、commit message、受け入れ条件から確認した変更意図 |
| Expanded surfaces | changed fileの直接consumer、parent、route、state、代表surface |
| Coverage / unknowns | 確認したsurface、未確認consumer、除外とその理由 |

変更fileは証拠の入口であり、レビュー対象を直接変更箇所だけに限定しません。shared primitive、global style / token、common component、theme等の変更は、代表的なconsumer surfaceへ展開し、確認できない範囲を未確認として残します。

commit rangeやPRは、Target snapshot / refに記録した既存のHead ref / SHA等の一意識別子を使います。working treeでは同じbase / head / branchでも別patchになり得るため、staged / unstagedのpatch hashとchanged path setをDiff identifierとして記録します。stagedまたはunstagedが空の場合も`empty`を記録し、後から同じbase / head / branchの別patchと区別できるようにします。

追加側と削除側を同じ重さで確認します。削除されたlabel、semantic element、focus、state、error recovery、responsive rule、copy、token等に等価な代替があるかを確認し、削除行の存在だけでfindingを断定しません。
<!-- agent-harness:uiux-change-scope-evidence:end -->

## 3. アプリ本体UIの証跡

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

アプリ本体UI（リポジトリが制御する独自アプリUIを含む）の変更では、該当画面・状態の変更前と変更後のscreenshotをPR本文へ添付します。GitHub共同作業面だけの変更は、後述の面別証跡に従います。

beforeは、実装前にbase snapshotから先行取得できます。base ref / SHA、対象surface・状態、viewport / device、runtime条件、artifact参照を記録し、これらが変わらない場合だけ比較証跡として再利用します。base snapshotのbeforeは、フロー監査で求める現在の監査実行・各stepの証跡を代替しません。

実装中または包括review中に取得したafterは`provisional`です。実装が完了し、同じ配送系列の包括reviewが収束した後、latest HEADで再取得したものだけを`final`としてPRの完了証跡に採用します。latest HEAD / base、所有path、review state、finding / fix、またはruntime条件の変更はafterを失効させ、review中なら`provisional`、収束後なら現行latest HEADで再取得します。失効前の画像は履歴または比較資料として残せますが、finalの根拠には使いません。

取得できない場合は、次を示します。

- 取得できなかった検証
- 理由
- 代替証跡
- 残るリスク
- 次に必要な確認

受け入れ条件または変更内容上screenshotが必須なのに取得できない場合は、完了扱いにしません。

### runtime / dev serverの実行記録

runtimeまたはdev serverを使用する場合は、起動前にownerを確定し、PID、process group、port、readiness確認、cleanup結果をbounded artifactへ記録します。cleanupではprocess groupの終了とport解放を確認します。既存プロセスを再利用する場合も、owner、対象port、実装との一致、readiness、cleanup責任を確認できることが条件です。owner不明、port衝突、readiness未確認、cleanup未確認の実行はcurrent-run証跡に採用せず、具体的なblockerまたは未確認範囲として報告します。runtimeを使用しない場合は、runtime resources / ports / cleanupを空として記録し、不要な実行記録を作りません。公開報告には運用識別子を必要最小限だけ記載します。

## 4. フロー監査の証跡

既存画面または複数ステップの体験を監査する場合は、対象面に応じた既存証跡へ次を追加します。

- 対象surface、対象ユーザー、ユーザー目的、監査対象タスク、取得手段、開始・完了状態
- 順序付きの重要な各ステップと、そこで行った操作、到達した画面・状態
- 現在の監査実行で取得し、保存後に対象画面・状態として検査済みのscreenshotのファイル名または参照、または取得不能の具体的なblocker
- navigation、focus、loading、validation、error recovery、empty state、motionなど、操作中に観測した挙動と確認手段
- 各findingが参照するステップ番号またはscreenshot、観測事実、ユーザー影響、推奨対応、P0 / P1 / P2、証跡上の限界
- 監査できなかった範囲、その理由、残るリスク、次に必要な確認

誤画面、誤状態、blank、loading中、文脈を隠すcrop、別window、half-rendered状態の画像は証跡へ採用せず、再取得します。以前のscreenshot、trace、cache、生成物は比較資料にできますが、現在の監査実行の証跡を代替しません。screenshotだけではsemantic structure、accessible name、contrast比、focus順序、keyboard完走、支援技術への通知、時間変化や回復挙動を確認済みとせず、別の実行証跡または未確認理由を示します。

フローを完走できない、重要ステップを取得・保存・検査できない、または必要な主張を実行証跡で支えられない場合はblockerです。取得手段・環境のblockerは証跡の状態として製品findingのseverityと分けます。監査できた部分を報告することはできますが、完全なフロー監査として完了扱いにしません。

UI変更レビューとフロー監査を併用する場合は、変更scopeの比較証跡と、各stepのcurrent-run証跡を同じ報告へ接続します。変更差分の証跡だけでフローを監査済みとせず、フローのscreenshotやstep記録だけでbase / headの変更由来を断定しません。

## 5. 変更由来findingの証跡
<!-- agent-harness:uiux-finding-provenance:start -->

差分を伴うUI変更レビューでは、各findingを次のいずれかへ分類します。分類はbase / head、diff、必要な描画・操作・test証跡で支え、単なる変更箇所の近さで決めません。

| Change status | 判定 |
|---|---|
| Introduced | head側の今回の変更が、新しい問題を作った。 |
| Regression | base側で成立していた品質が、今回の変更で弱くなった。 |
| Pre-existing | base側でも同じ問題があり、今回の変更が作成・弱体化していない。 |

IntroducedとRegressionは今回の変更のfindingとしてP0 / P1 / P2、修正状態、証跡を記録します。Pre-existingは影響に応じた優先度を記録した上で、今回の変更責任、変更起因findingの件数・P0 / P1 / P2集計から分離し、必要なら別Issueまたはscope変更として追跡します。変更目的または安全性を阻害するP0/P1等のblocking findingは完了可否と判定理由へ残し、別Issue化だけで完了扱いにせず、scopeと完了判断を明示的に見直します。

同じroot causeは一件へ統合し、影響するsurfaceを列挙します。未確認consumerをreview済み、またはPre-existingを今回の修正済みとして表現しません。
<!-- agent-harness:uiux-finding-provenance:end -->

## 6. GitHub共同作業面の証跡

Issue / PR template、repository Markdown、workflowの入力・説明などでは、次を確認します。

- 変更した文言、項目、順序、必須性、設定の差分
- Markdown、form、YAML、frontmatterなどの構造
- link、command、移動先file
- 公開安全性
- previewまたは実ページ確認が必要か
- 実行していない検証と残るリスク

GitHubが所有し、リポジトリが変更していないlayout、keyboard、focus、loading、permission stateへ、アプリ本体UIと同じstate matrixやaccessibility証跡を要求しません。GitHub共同作業面だけの変更では、アプリ本体UI用のscreenshotやruntime / dev serverを要求せず、owner / PID / process group / port / readiness / cleanupの実行記録も不要です。screenshotまたはpreviewは、リポジトリが制御する視覚構成・操作が実質的に変わる場合、受け入れ条件に含まれる場合、または明示依頼がある場合に限り追加します。

## 7. 完了ゲート

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
- beforeがbase snapshotへ、afterが実装・包括review収束後のlatest headへ束縛され、review中のafterを`provisional`として扱っている。
- runtime / dev serverを使った場合、owner、PID、process group、port、readiness、cleanupを確認している。

### UI変更レビュー（差分を伴う場合）

- target snapshot / ref、base / head、変更意図、追加側・削除側が記録されている。
- changed fileから直接consumerへ展開し、shared primitive、global token、common component等は代表surfaceを追加確認している。
- coverage、未確認consumer、除外理由を示している。
- IntroducedとRegressionを今回の判定対象としている。
- Pre-existingの通常の変更起因件数・責任を分離している。ただし、変更目的または安全性を阻害するP0/P1等のblocking findingは完了可否・判定理由に残し、scopeと完了判断を明示的に見直している。

### GitHub共同作業面

- 文言、項目、順序、必須性、構造、link、公開安全性を変更範囲に比例して確認している。
- アプリ本体UI用の前後screenshot、runtime / dev server、またはその実行記録を要求していない。

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
- review decision recordと停止条件は [`docs/agent-harness.md`](../agent-harness.md) の正本を参照し、terminalなfocused reviewを完了条件へ反映する。
- 高コストのfull gate finalizationはfocused review terminalの後に1回だけ行い、同一input closure・execution conditionsで成功したgateは既存evidenceを再利用する。

ソースコード変更でコードレビューが提供されない場合、代替自己レビューは補助証跡に限り、マージ可能状態の代替にしません。同じheadでclean reviewを複数回集める必要はありません。指摘対応でheadが変わった場合だけ、CIと該当reviewを再確認します。mergeまたはcloseは別の明示指示がある場合だけ行います。

## 8. 推奨検証

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

## 9. 報告

`templates/completion-gate-report.md` を使うか、同等の情報をPR本文へ記録します。空の項目を定型的なN/Aで埋めるより、今回の対象面と未確認範囲が明確な報告を優先します。
