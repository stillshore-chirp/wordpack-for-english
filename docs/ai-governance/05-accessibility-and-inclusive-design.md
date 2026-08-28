# アクセシビリティとインクルーシブデザイン

アクセシビリティは後付けではありません。UI/UX変更の完了条件です。自動検査だけで合格とせず、利用者が主要taskを知覚し、理解し、操作し、結果と状態を受け取れることを、source、描画、操作の証跡で確認します。

## 1. 基本方針

- 見えるだけでなく、知覚できること。
- クリックできるだけでなく、keyboardや支援技術でも操作できること。
- 文言があるだけでなく、名前、role、state、関係が伝わること。
- 現在状態が視覚的に見えるだけでなく、必要な変化が支援技術にも伝わること。
- native elementとbrowser標準挙動を優先し、custom widgetは選んだinteraction contractを一式で実装すること。
- 狭幅、文字拡大、forced colors、reduced motion等、想定する利用環境でtaskを継続できること。
- 数値、key mapping、ARIA patternは開始点または適用条件であり、既存design system、対応環境、ユーザーtask、標準の例外を確認して適用すること。

## 2. Native semantics

- actionには`button`、navigationには`a`、入力には適切なform controlを使う。`div`や`span`へclick handlerを付けて代用しない。
- native elementで成立する場合はARIAを追加しない。誤ったARIAで標準の名前、role、stateを上書きしない。
- list、table、heading、landmarkは見た目だけで作らず、情報構造と一致するelementを使う。
- `main`、navigation、補助領域、反復contentのskip手段を、page構造に応じて用意する。

## 3. Keyboard操作

確認事項:

- 主要taskをkeyboardだけで完了できるか。
- focus順序がDOM、視覚順序、操作順序と一致するか。
- pointerで可能な操作にkeyboard経路があるか。
- Tab / Shift+Tabはwidget間、arrow keyは採用したtabs、menu、listbox等の複合widget内というpatternに合うか。
- EnterとSpaceのactivation、Escapeのdismiss、Home / End等が採用したwidget patternと一致するか。
- 正の`tabindex`で順序を補正していないか。DOM順を直し、`0`と`-1`を意図的に使う。
- keyboard shortcutが入力、支援技術、browser標準操作を奪わず、表示された説明と実際の挙動が一致するか。

P0例（`02-uiux-review-framework.md`に照らし、主要taskへの影響が確認できる場合）:

- keyboardで主操作に到達または実行できない。
- pointerでは可能だがkeyboardでは不可能なpathがある。
- modal、menu、popover等からkeyboardで抜けられない。

## 4. 複合widget

複数のfocusable elementを一つの操作単位として扱うUIは、見た目が似ているだけでpatternを混ぜません。

- native `select`、`details`、radio等で目的を満たせるかを先に検討し、custom実装を増やさない。
- customにする場合は、tabs、menu、listbox、combobox、tree、grid、radio group、toolbar等から目的に合うpatternを選び、entry、内部移動、activation、dismiss、exit、stateを明示する。
- widgetへ入るTab位置と出るTab位置を定め、内部のarrow key、Home / End、Enter / Space、Escapeの挙動を選んだpatternに揃える。Tabだけで内部の全itemを順番に通すか、roving `tabindex` / `aria-activedescendant`で一つのentry pointにするかは、操作内容と支援技術の対応を確認して決める。
- `aria-expanded`、`aria-controls`、`aria-selected`、`aria-checked`、`aria-activedescendant`等は、実際の表示・focus方式と一致させ、視覚的なselectedとkeyboard focusを混同しない。
- nested widgetや編集可能なcellでは、親のarrow keyが子の入力・caret操作を奪わない境界を定める。
- hoverやpointer位置だけで開くcontentは、focus、keyboard、touchでも到達でき、別の操作を妨げずdismissできること。

## 5. Focus表示・移動・復帰

- keyboard focusは常に視認でき、sticky header、overlay、scroll containerに隠れないこと。
- pointerとkeyboardの意図を分ける場合は`:focus-visible`を使い、`outline: none`だけを残さない。custom focus indicatorは隣接する背景と想定するtheme / forced colorsで見えることを確認する。
- modal / dialogを開いた時は、目的に適した要素へfocusを移し、modalの方式に応じてbackgroundを操作・読み上げ対象から外す。
- dialog、menu、popoverを閉じた時は、削除されていない限りtriggerまたは論理的な次の位置へfocusを戻す。Escape、outside click、cancel、submit失敗の経路を別々に確認する。
- route変更、error発生、項目の追加・削除後に、focusがbodyや消えたelementへ失われないようにする。validation後は最初のerrorまたはerror summaryへ、結果更新後は文脈を失わない位置へ移すか、移動しない理由を明確にする。
- focusを移す場合も、ユーザーの入力・選択・スクロール位置を不意に失わせない。自動focusは毎回の再renderで繰り返さない。

## 6. 名前・role・state・value

確認事項:

- button、link、input、menu、tab等に、目的を説明するaccessible nameがあること。
- icon-only controlは可視tooltipだけに依存せず、支援技術へ明確な名前を提供する。
- visible labelの文字列がaccessible nameへ含まれ、音声入力で表示名を使って操作できること。
- expanded、selected、pressed、checked、current、invalid、busy、disabled等のstateが必要な時に伝わること。
- decorationはaccessibility treeから除外し、focusable element自体へ`aria-hidden`を付けない。
- 表示label、accessible name、説明、対象範囲が互いに矛盾せず、dynamicなvalue更新も読み取り可能であること。

## 7. Formと入力支援

確認事項:

- 各入力に永続的な可視labelを付け、placeholderだけをlabelにしない。
- `name`、`autocomplete`、`type`、`inputmode`を入力内容に合わせ、pasteやpassword managerを妨げない。
- hintとconstraintは入力前または入力中に確認でき、errorだけに情報を閉じない。
- validation errorは入力近くへ表示し、`aria-invalid`と`aria-describedby`等で対象と説明を結ぶ。
- submit前からactionを無効化して理由を隠すより、実行後に具体的な修正方法を示せるか検討する。
- 本当に利用不能なnative controlは`disabled`を使う。focus可能なまま説明を提供する場合は、pointer、keyboard、submitの挙動を同時に制御する。
- error後も入力済みdataを保持し、複数errorは全体と個別の両方から把握できること。

## 8. 見出し・landmark・構造

確認事項:

- pageと主要領域に内容を説明するheadingがあり、意味上の階層が追えること。
- heading levelを見た目のsize目的で選ばず、visual treatmentはCSSへ分離する。
- repeated navigationやchromeが本文より前にある場合、主要contentへ移動する手段を検討する。
- anchor先はsticky headerに隠れず、focus移動後に現在位置が分かること。
- table、list、definition、groupの関係がaccessibility treeにも現れること。

## 9. Contrastとforced colors

- 通常text、補助text、placeholder、link、icon、border、input、focus indicatorを、実際に重なるforeground / background pairで確認する。透明度、gradient、image、hover、selected、disabled、error、dark modeを含める。
- 色だけでerror、success、warning、selection、required、disabledを伝えず、text、icon、形、境界、位置等を併用する。
- `forced-colors`が有効な環境では、outline、control境界、selected state、icon、link、focusが消えないことを確認する。system colorの利用を妨げる指定や`forced-color-adjust: none`は、必要性、代替表示、対象環境を確認して採否を記録する。
- contrast比の数値は、適用するWCAG達成基準、対象のstate、例外、既存design systemを確認して使う。数値だけでseverityや完了可否を機械的に決めない。

## 10. Target size

- 操作対象が小さすぎず、隣接する操作対象との間隔が十分であること。
- touch環境で誤操作しにくく、小さいiconだけで危険操作を置かないこと。
- 見た目を小さく保つ場合もhit areaを確保し、隣接領域と重ならないこと。

## 11. Dynamic contentと状態通知

- 保存完了、読み込み、件数更新、validation、通信失敗等が視覚的に分かり、どの領域・操作の結果か分かること。
- controlに直接結びつくerrorは対象fieldと関連付け、routine updateは`status`等のpoliteな通知を使う。緊急性のないtoastや件数更新をassertiveに読み上げない。
- live regionは表示後に後付けしたり頻繁に置き換えたりせず、安定したregionへ意味のある差分を更新する。同じmessageを繰り返す必要がある場合も、対象支援技術で通知されることを確認する。
- actionや重要errorを含むnotificationは、読む前に消えず、dismissまたは再確認できる到達手段を持つこと。通知のためだけにfocusを奪わない。
- loadingでは対象領域、既存dataの扱い、完了後の変化、再試行・cancelの有無が分かること。成功、empty、partial、errorを同じ見た目へ潰さない。

## 12. Zoom、reflow、text resize

- 対応要件にWCAG 2.2を採用する場合、200%までのtext resizeと、縦スクロール主体では320 CSS px、横スクロール主体では256 CSS px相当のreflowを確認し、情報・機能の損失、不要な二方向scroll、clip、overlap、到達不能を残さない。二次元の意味が本質のtable等は、例外と代替到達手段を確認する。
- text containerへ固定heightを置かず、文字拡大、text spacing、長文、翻訳相当の伸長でcontentやcontrolが欠落しないこと。
- viewport設定でuser zoomを制限しない。sticky / fixed要素、safe area、virtual keyboard、scroll位置がcontentやfocusを隠さないこと。
- 省略や折り返しで判断に必要な情報を隠さず、全文表示、展開、詳細画面などへ到達できること。長いID・URL等を壊さずに扱う方針も定める。

## 13. Motionと時間

- `prefers-reduced-motion`を尊重し、移動、scale、parallax、autoplay等を停止または穏やかな代替へ変える。設定変更が実行中に反映される場合の状態も確認する。
- motionを唯一のstate feedbackにせず、text、icon、形、境界、色等の静的signalを併用する。interactionで始まるmotionを止められる設計も検討する。
- actionやerrorを含むtime-limited contentは、停止、延長、dismiss、再確認ができること。flashing、rapid motion、scroll連動表現は必要性と安全性を確認する。

## 14. 認知accessibility

- 画面目的、現在地、対象範囲、最初の行動が明確であること。
- 一貫した用語を使い、内部IDや実装用語を押し付けない。
- constraint、選択中state、過去入力を画面に出し、不要な記憶や推測を要求しない。
- errorを避け、起きた場合も原因、影響、修正方法、data保持を示す。
- 初心者向け説明は、熟練者の反復taskを恒常的に妨害しない。

## 15. 数値とpatternの扱い

導入先のdesign system、対応要件、対象browser、支援技術を優先します。次は確認の出発点であり、文脈を無視した一律のhard gateではありません。

- 通常textのcontrast 4.5:1、大きいtextや必要な非text UI部品の3:1は、該当するWCAG達成基準と例外を確認して測る。
- 操作対象24×24 CSS pxは、WCAG 2.2のTarget Size (Minimum)を適用する場合の確認点とし、同等の間隔、例外、touch中心の文脈を含めて判断する。
- 本文16px、長文のline-height 1.5、touch中心でより大きいtargetは、読みやすさを確認する目安として使う。既存tokenや実際のtypeface・画面密度がある場合は、それとの整合を優先する。
- 200% text resize、320 CSS pxまたは256 CSS px相当のreflow、forced colors、reduced motionは、対応要件に該当する環境で検証する。未対応環境の推測でPassにしない。
- ARIA patternのkey mappingは、patternの名前だけで合格とせず、entryからexitまでの操作、state、focus、nested controlを一つのtaskで確認する。

## 16. 重大な影響の例

この文書の確認事項をP0/P1/P2へ分類する場合は、`02-uiux-review-framework.md`のseverityを使い、ユーザーtaskへの影響と証跡を併記します。次は重大な影響になり得る例です。

- keyboardまたは支援技術で主要taskを完了できない。
- focusが見えない、失われる、overlayから抜けられない、または閉じた後に論理的位置へ戻れない。
- interactive controlにaccessible nameがなく、対象や結果を判断できない。
- status、error、selected等が通知されず、または色・motionだけで伝えられる。
- 対応要件に該当するzoom / reflowで主要contentやcontrolがclip、overlap、到達不能になる。
- reduced motionの希望を無視する自動再生や大きなmotionがtask継続を妨げる。

## 17. 検証証跡

変更範囲に応じて次を組み合わせ、実行できない確認は理由と残riskを記録します。

- keyboard traversal、複合widgetのentry / 内部移動 / exit、focus表示・移動・復帰。
- browser accessibility treeとaccessible name / role / state / value、必要に応じたscreen readerとbrowserの読み上げ・操作。
- axe-core等の自動検査。ただし自動検査だけで合格としない。
- 実際のforeground / background pairのcontrast測定、dark mode、forced colors、focus indicator。
- 200% zoom、320 CSS pxまたは256 CSS px相当、text spacing、長文・長いlabel・翻訳相当の伸長、truncationからの全文到達。
- reduced motion、notificationの保持時間、autoplay、pause / dismiss / 再確認。
- screenshotは見えている構造・stateの補助証跡とし、accessible name、focus順序、支援技術通知、時間変化、回復挙動を静止画だけで確認済みとしない。証跡の採否と完了判定は`03-evidence-and-completion-gates.md`に従う。

## 18. 参照する標準

- W3C Web Content Accessibility Guidelines (WCAG) 2.2（keyboard、focus、contrast、resize、reflow、status messages等の適用条件）
  https://www.w3.org/TR/WCAG22/

- W3C WAI-ARIA Authoring Practices: Developing a Keyboard Interface（複合widgetのfocusとkeyboard原則）
  https://www.w3.org/WAI/ARIA/apg/practices/keyboard-interface/

- W3C WAI-ARIA Authoring Practices: Patterns（patternごとの操作契約）
  https://www.w3.org/WAI/ARIA/apg/patterns/

- CSS Color Adjustment Module Level 1（`forced-colors`とsystem color）
  https://www.w3.org/TR/css-color-adjust-1/

- Media Queries Level 5（`prefers-reduced-motion`）
  https://www.w3.org/TR/mediaqueries-5/
