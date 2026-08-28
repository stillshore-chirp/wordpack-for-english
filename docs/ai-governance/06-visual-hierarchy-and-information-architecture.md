# 視覚階層と情報設計

視覚階層は装飾ではありません。ユーザーの注意、理解、現在地、行動選択を支援する構造です。文字・色・余白・面・位置・motionは、情報の意味とtaskの優先度を伝えるために使います。keyboard、semantic structure、focus、状態通知の正本は`05-accessibility-and-inclusive-design.md`と`08-state-design-and-error-recovery.md`を優先します。

## 1. 基本原則

- 重要なものを重要に見せる。
- 関連するものを近くに置く。
- 異なるものを区別する。
- 迷う前に次の行動を示す。
- 情報量を減らすだけでなく、優先度を明確にする。
- 視覚順、DOM順、keyboard順、読み上げ順を矛盾させない。
- 装飾で問題を覆わず、情報構造と優先度を先に直す。

## 2. 3秒確認

画面を3秒見た前提で、次に答えられる必要があります。

- 何の画面か。
- 今どこか。
- 何が重要か。
- 最初に何をすべきか。
- どの情報が補助か。

答えられない場合は、観測事実とtaskへの影響を記録し、`02-uiux-review-framework.md`のseverityに照らして、heading、説明、視覚階層、状態表示、labelを修正します。3秒確認だけでseverityを機械的に決めません。

## 3. 主操作

確認事項:

- 意思決定領域ごとに主操作が明確か。
- 主操作が複数あって競合していないか。
- 危険操作が主操作より強く見えていないか。
- 主操作が画面下部、隅、アイコン、薄いリンクに埋もれていないか。
- 主操作のラベルは結果を示しているか。
- 複数の主操作が競合する場合は、taskの順序、頻度、取り消しやすさを基準に整理しているか。
- 主要taskの途中で、無関係なpromotion、secondary action、長い説明がattentionを奪っていないか。

## 4. グルーピング

確認事項:

- 関連する情報と操作が近くにあるか。
- カード、セクション、表、リストの境界が分かるか。
- どの操作がどの対象に効くか分かるか。
- フィルタ、検索、件数、タブの対象範囲が明確か。
- 関連する情報、入力、説明、error、actionを一つのgroupとして読めるか。
- group内の余白とgroup間の余白に差があり、同じ階層の要素が共有する基準線へ揃っているか。
- repeated row、card、tableでlabel、value、status、actionの位置が一貫しているか。
- expanded hit area、tooltip、popoverが隣接controlやreading orderを壊していないか。

## 5. タイポグラフィ

確認事項:

- 見出し、本文、補助情報、メタ情報の差が明確か。
- 本文が小さすぎないか。
- 行間が詰まりすぎていないか。
- 長文の行長が長すぎないか。
- 日本語の折り返しで意味が取りにくくなっていないか。
- 数字、単位、日時、件数が読み取りやすいか。

### Font loadingとfallback

- 使用するfont family、weight、styleが実際に読み込まれ、意図しない合成や欠落glyphに依存していないか。
- font loading中またはfallback時にも、本文、見出し、label、actionの階層と意味が保たれるか。fontのswapで、読み位置や操作対象が不意に移動しないか。
- `font-display`、preload、subset等の方式は、対応browser、初回表示、再訪、通信失敗の挙動を確認して選ぶ。特定の値を全用途へ一律適用しない。

### 文字列伸長とtruncation

- 見出し、説明、badge、table cell、URL、長い単語、翻訳相当の伸長ごとに、wrap、overflow、省略の方針を定める。
- 省略された情報が判断に必要なら、展開、詳細画面、コピー可能な全文など、同じ文脈から全文へ到達する手段を用意する。tooltipだけを唯一の経路にしない。
- 固定heightや一行固定が、long content・text resize・localizationで重要な情報やactionを隠さないか確認する。

### 動的な数値

- 件数、timer、価格、進捗など更新される数字は、符号、単位、桁区切りを含めてscanできるか確認する。
- 数字の更新で周囲のlabelやactionが揺れる場合は、幅の確保や`tabular-nums`等を検討する。ただし全ての数値へ適用せず、実際のlayout shiftと読みやすさで判断する。

## 6. 余白と密度

確認事項:

- 余白が情報のまとまりを示しているか。
- 密度が高すぎて主操作が見えなくなっていないか。
- 低密度すぎて一覧性や熟練者効率を損ねていないか。
- モバイルや狭幅で余白が崩れていないか。

## 7. スキャン性

ユーザーは画面を上から順に丁寧に読みません。短時間で必要な情報を探します。

確認事項:

- 見出しだけで概要が掴めるか。
- ラベルや値の対応が分かるか。
- 状態や件数がすぐ分かるか。
- 重要な警告やエラーが埋もれていないか。

## 8. 情報設計

確認事項:

- ユーザーの目的に沿った分類になっているか。
- 開発者都合の構造が画面に漏れていないか。
- ナビゲーション階層が深すぎないか。
- 現在地と戻り先が分かるか。
- 同じ概念に複数の名前を使っていないか。

## 9. Adaptive layout

- breakpointはdevice名ではなく、内容・action・比較が成立しなくなる境界で決める。
- 同じcomponentが異なる幅の親へ配置される場合は、既存環境が許す範囲でcontainer query等のcomponent単位の適応を検討する。query containerを追加する時は、親のサイズ制約、fallback、nested containerの影響を確認する。
- narrow width、200% zoom、文字拡大、長文、大量dataでhierarchy、主操作、scope、state表示が崩れないこと。
- 視覚上の並べ替えでDOM / keyboard / reading orderを壊さず、方向依存の余白・位置にはlogical propertyを優先する。
- sticky / fixed要素がmain content、focus、error、actionを隠さないこと。hidden / collapsed contentへ到達するaffordanceを残す。

## 10. Colorとtheme

- 生のcolor値を局所追加する前に、既存のsemantic tokenを利用する。役割が不足する場合は、別の意味のtokenを借用せず新しい役割を定義する。
- 同じcolorへ複数の意味を持たせず、success、warning、error、selection、link、primary actionの役割を一貫させる。
- light、dark、system、increased contrast、forced colors等のappearanceを、単純な反転ではなく各state・各foreground / background pairで確認する。技術的なforced-colorsの扱いは`05-accessibility-and-inclusive-design.md`に従う。
- theme切り替え時に、現在のfocus、入力、selection、scroll位置、statusを不意に失わず、切り替え中のflashや一時的な読めない配色を残さない。
- 色だけでscopeやstateを伝えず、text、icon、形、位置、border等を併用する。強い塗りは一つの意思決定領域の主操作へ集中させる。

## 11. Motion

- motionは階層、状態遷移、因果関係を理解させる場合に使い、高頻度操作へ注意を奪うanimationを常用しない。
- `prefers-reduced-motion`では、移動、scale、parallax、autoplay等を停止または穏やかな代替へ変える。motionだけを唯一のstate feedbackにせず、静的なsignalを残す。
- pointer操作や連続入力中も中断・再操作できるtransitionを優先し、一度始まると割り込めない演出や、layoutを毎frame再計算するmotionは必要性と性能を確認する。
- `transition: all`や不要な`will-change`を常用せず、変化するpropertyと実測した性能影響を記録する。

## 12. Visual finish

- 同一surfaceでicon family、stroke weight、size、角の性格を揃え、隣接する文字との光学的な強さを合わせる。幾何学的な中央揃えが視覚的にずれるiconは、実際の描画を見て補正する。
- radius、border、shadow、surfaceの階層は既存tokenへ寄せ、入れ子の角やdepthが矛盾しないようにする。装飾を増やす前に情報構造を直す。
- hover、focus、active、selected、disabled、loading、success、errorの各stateで、反応が一貫し、情報と操作対象が消えないこと。
- border、shadow、gradient、icon、animationは、contrast、forced colors、reduced motion、長文、狭幅で重要情報を隠さないこと。
- visual polishの良否はsourceだけで確定せず、代表的なrenderとstateで確認する。仕上げの一貫性とtaskの理解・操作を切り離さない。

## 13. 数値とheuristicの扱い

既存design system、対応要件、対象browser、コンテンツの言語・量を優先します。breakpoint、行長、余白、font size、animation duration、container幅などは確認の出発点であり、数値だけでP0/P1/P2や完了可否を機械的に決めません。severityは`02-uiux-review-framework.md`に従い、ユーザーtaskへの影響と実際の証跡を併記します。

## 14. 検証証跡

変更範囲に応じて次を記録し、実行できない確認は理由と残riskを明示します。

- viewportだけでなく、主要componentのcontainer幅、zoom、文字拡大、RTL / LTR、theme、state、代表的なlong contentとlarge data。
- font request、読み込み済みfamily / weight、fallback、wrap、truncationからの全文到達、動的な数値のlayout shift。
- 3秒確認、主操作とscopeのvisual hierarchy、主要stateのrender、必要に応じたscreenshotまたはvisual diff。
- 実際に重なるforeground / background pairのcontrast、dark / light / forced colors、focus indicator。
- reduced motion、初回表示、enter / exit、hover、連続入力、通知・loadingの時間変化。
- screenshotは見えている構造・stateの補助証跡とし、semantic structure、accessible name、focus順序、支援技術通知、回復挙動を静止画だけで確認済みとしない。アクセシビリティの検証と証跡の採否は`05-accessibility-and-inclusive-design.md`および`03-evidence-and-completion-gates.md`に従う。

## 15. 視覚階層の失敗例

- 主操作より補助ボタンが目立つ。
- 画面タイトルが抽象的すぎる。
- 空状態が単なる「データがありません」で終わる。
- タブの対象範囲が分からない。
- フィルタ件数が全体件数か表示件数か分からない。
- 危険操作が小さなアイコンだけで置かれている。
- 重要なエラーが画面上部にだけ出て、入力欄付近にない。

## 16. 参照する標準・実務知見

- W3C Web Content Accessibility Guidelines (WCAG) 2.2（visual presentation、contrast、resize、reflow、text spacing等）
  https://www.w3.org/TR/WCAG22/

- CSS Fonts Module Level 4（font loadingと`font-display`）
  https://www.w3.org/TR/css-fonts-4/

- CSS Text Module Level 4（wrap、line breaking、overflow）
  https://www.w3.org/TR/css-text-4/

- CSS Containment Module Level 3（container query）
  https://www.w3.org/TR/css-contain-3/

- CSS Color Adjustment Module Level 1（`forced-colors`、system color、`color-scheme`）
  https://www.w3.org/TR/css-color-adjust-1/

- Media Queries Level 5（`prefers-reduced-motion`）
  https://www.w3.org/TR/mediaqueries-5/

- デジタル庁デザインシステム: タイポグラフィ（アクセシビリティ）
  https://design.digital.go.jp/dads/foundations/typography/accessibility/
