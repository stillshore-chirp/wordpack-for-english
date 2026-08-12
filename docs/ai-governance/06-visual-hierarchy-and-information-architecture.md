# 視覚階層と情報設計

視覚階層は装飾ではありません。ユーザーの注意、理解、現在地、行動選択を支援する構造です。文字・色・余白・面・位置は、情報の意味とtaskの優先度を伝えるために使います。具体的なlayout、typography、color、icon、motionの実装判断は`15-interface-engineering-quality.md`を正本とします。

## 1. 基本原則

- 重要なものを重要に見せる。
- 関連するものを近く、異なるものを明確に分ける。
- 操作と対象を同じ文脈に置く。
- 迷う前に現在地、対象範囲、次のactionを示す。
- 情報量を減らすだけでなく、何を先に理解すべきかを明確にする。
- 視覚順、DOM順、keyboard順、読み上げ順を矛盾させない。
- 装飾で問題を覆わず、情報構造と優先度を先に直す。

## 2. 3秒確認

画面を3秒見た前提で、次に答えられる必要があります。

- 何の画面か。
- 今どこか。
- 何が重要か。
- 最初に何をすべきか。
- どの情報が補助か。
- 操作がどの対象へ効くか。
- 待機、失敗、完了など現在stateは何か。

答えられない場合は、heading、説明、placement、grouping、state表示、labelを見直します。画面全体を説明文で補う前に、構造だけで伝わる範囲を増やします。

## 3. 主操作と意思決定領域

- 一つの意思決定領域で主操作を明確にする。
- 複数の主操作が競合する場合は、taskの順序、頻度、reversibilityを基準に整理する。
- 危険操作を主操作より強く見せず、対象・影響・取り消し可否を近くに置く。
- 主操作を画面下部、隅、icon、薄いlinkへ偶発的に埋めない。
- action labelは実行後の結果を示す。
- 主要taskの途中で、無関係なpromotion、secondary action、長い説明がattentionを奪わないこと。

## 4. Groupingとalignment

- 関連する情報、入力、説明、error、actionを一つのgroupとして読めるようにする。
- group内の余白とgroup間の余白に差を付け、lineやcardを増やす前にspaceとalignmentを使う。
- 同じ階層の要素は共有する基準線へ揃える。
- controlは静的contentと区別でき、どの対象に作用するか位置関係から分かること。
- repeated row、card、tableで、label、value、status、actionの位置を一貫させる。
- expanded hit area、tooltip、popoverが隣接controlやreading orderを壊さないこと。

## 5. Scope・selection・state

次の対象範囲を曖昧にしません。

- searchが何を検索するか。
- filterがどのlist / tab / sectionへ効くか。
- 件数が全体、filter後、表示中のどれか。
- selectionが現在page、全結果、手動選択のどれか。
- bulk actionが何件・どの対象へ作用するか。
- loading / errorがpage全体か局所領域か。
- success messageがどの操作結果か。

色や一時的なanimationだけでscopeやstateを示さず、text、位置、icon、境界、heading等を併用します。

## 6. Typographyによる階層

- heading、body、label、helper、metadata、status、actionの役割が見た目から区別できること。
- font sizeとweightを増やしすぎず、semantic scaleへ寄せる。
- 見出しの視覚的な強さが意味上の親子関係と矛盾しないこと。
- bodyの行長、line-height、paragraph間隔が連続読解を助けること。
- 数値、単位、日時、件数はscanしやすく、更新時に不要なlayout shiftを起こさないこと。
- 長い日本語、英数字、翻訳相当の伸長でheadingやactionが誤解される位置へ折り返されないこと。
- 省略された重要情報へ全文確認手段があること。

具体的なfont、wrap、measure、tabular numbers、mobile inputは`15-interface-engineering-quality.md`に従います。

## 7. 余白とdensity

- 余白が情報のまとまりと優先度を示すこと。
- 高densityで主操作、status、warningが埋もれないこと。
- 低densityで一覧性、比較、熟練者効率を損なわないこと。
- compact modeやlarge datasetでは、target size、scan性、誤操作のbalanceを確認する。
- mobile / narrow widthで、desktop用の余白がcontentを圧迫しないこと。
- full-bleedの背景・mediaと、safe area内に置くtext / controlを区別する。

## 8. Scan性

ユーザーは画面を上から順に丁寧に読みません。短時間で必要な情報を探せるようにします。

- headingだけでsectionの役割が分かる。
- labelとvalueの対応が一定である。
- status、件数、期限、error、warningを探しやすい。
- repeated contentの中で、差分とactionが見つかる。
- 長いdescriptionを読まなくても主taskを開始できる。
- tableやlistでは、重要列、sort、filter、selection、paginationの関係が分かる。
- empty、no-results、permission、errorを同じ見た目へ潰さない。

## 9. 情報設計とnavigation

- 分類と用語がユーザーの目的・mental modelに合うこと。
- data model、内部ID、開発者都合のboundaryを画面構造へ漏らさないこと。
- 同じconceptに複数の名前を使わないこと。
- navigation階層を深くしすぎず、現在地と戻り先を示すこと。
- tab、breadcrumb、side navigation、page headingが互いに異なる現在地を示さないこと。
- global action、page action、row actionのplacementを混同しないこと。
- progressive disclosureでは、hidden contentが存在する手がかりと開閉stateを示すこと。
- deep link、back / forward、reload後も、userが意味のあるstateへ戻れること。

## 10. Adaptive layout

- breakpointはdevice名ではなく、内容・action・比較が成立しなくなる境界で決める。
- narrow width、200% zoom、文字拡大、長文、大量dataでhierarchyが崩れないこと。
- 視覚上の並べ替えでDOM / keyboard / reading orderを壊さないこと。
- RTLではleading / trailingを基準にし、physical left / rightへ不要に依存しないこと。
- sticky / fixed要素がmain content、focus、error、actionを隠さないこと。
- hidden / collapsed contentへ到達するaffordanceがあること。

## 11. 視覚階層のP0

- 初見で画面目的、現在地、対象範囲、最初のactionが分からない。
- 主操作が見つからない、または別のactionと誤認する。
- 危険操作がiconだけ、またはsafe actionより強く見える。
- error、permission、loading、empty、successのstateを誤認する。
- operation scopeやselection scopeが不明で、意図しない複数対象へ作用し得る。
- narrow width、zoom、long contentで主情報・主操作がclip、overlap、到達不能になる。
- 視覚順とkeyboard / reading orderが矛盾し、主要taskを正しい順で理解・操作できない。

## 12. 視覚階層のP1

- primary / secondaryの強弱がずれ、task開始や判断が遅くなる。
- grouping、alignment、densityの不整合が複数箇所でscan性を損なう。
- search、tab、filter、件数、selectionのscopeが曖昧だが回避可能。
- heading、body、metadata、statusの階層が不安定。
- navigation、現在地、戻り先の対応が分かりにくい。

## 13. Evidence

- 対象screen、flow、state、viewport、zoom、theme、directionを記録する。
- 3秒確認と最初のactionを、実際の描画で確認する。
- narrow、long-content、large-data、error等の代表stateをscreenshotまたはmanual resultで残す。
- sourceだけでvisual claimを確定せず、描画できない場合はNot verifiedとする。
- findingにはcurrent、expected、user impact、location、P0/P1/P2を付ける。
- 変更差分reviewではIntroduced / Regression / Pre-existingを`16-change-scoped-interface-review.md`に従って分ける。
