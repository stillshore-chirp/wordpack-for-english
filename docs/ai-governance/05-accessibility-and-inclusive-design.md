# アクセシビリティとインクルーシブデザイン

アクセシビリティは後付けではありません。UI/UX変更の完了条件です。自動検査だけで合格とせず、利用者が主要taskを知覚し、理解し、操作し、結果と状態を受け取れることを、sourceと描画・操作の両方で確認します。

## 1. 基本方針

- 見えるだけでなく、知覚できること。
- クリックできるだけでなく、keyboardや支援技術でも操作できること。
- 文言があるだけでなく、名前、role、state、関係が伝わること。
- 現在状態が視覚的に見えるだけでなく、必要な変化が支援技術にも伝わること。
- native elementとbrowser標準挙動を優先し、custom widgetは必要なinteraction contractを実装すること。
- 一部のユーザーだけでなく、狭幅、拡大、forced colors、reduced motion等の利用環境で使えること。

## 2. Native semantics

- actionには`button`、navigationには`a`、入力には適切なform controlを使う。`div`や`span`へclick handlerを付けて代用しない。
- native elementで成立する場合はARIAを追加しない。誤ったARIAで標準の名前、role、stateを上書きしない。
- list、table、heading、landmarkは見た目だけで作らず、情報構造と一致するelementを使う。
- primary `main`、navigation、補助領域、反復contentのskip手段を、page構造に応じて用意する。

## 3. Keyboard操作

確認事項:

- 主要taskをkeyboardだけで完了できるか。
- focus順序がDOM、視覚順序、操作順序と一致するか。
- pointerで可能な操作にkeyboard経路があるか。
- Tab / Shift+Tabはwidget間、arrow keyはtabs、menu、listbox等の複合widget内という既存patternに合うか。
- EnterとSpaceのactivation、Escapeのdismiss、Home / End等が採用したwidget patternと一致するか。
- 正の`tabindex`で順序を補正していないか。DOM順を直し、`0`と`-1`を意図的に使う。
- focusが閉じ込められず、keyboard shortcutが入力やbrowser標準操作を奪わないか。

P0例:

- keyboardで主操作に到達または実行できない。
- pointerだけで到達できるpathがある。
- modal、menu、popover等からkeyboardで抜けられない。

## 4. Focus表示・移動・復帰

- keyboard focusは常に視認でき、sticky header、overlay、scroll containerに隠れないこと。
- pointerとkeyboardの意図を分ける場合は`:focus-visible`を使い、`outline: none`だけを残さない。
- custom focus indicatorは、隣接するすべての背景とforced colorsで見えることを確認する。
- modal / dialogを開いた時は、目的に適した要素へfocusを移し、backgroundを操作対象から外す。
- dialogを閉じた時は、削除されていない限りtriggerまたは論理的な次の位置へfocusを戻す。
- route変更、error発生、項目追加・削除後に、focusがbodyや消えたelementへ失われないようにする。
- validation後は最初のerrorまたはerror summaryへ、結果更新後は文脈を失わない位置へfocusを扱う。

## 5. 名前・role・state・value

- button、link、input、menu、tab等に、目的を説明するaccessible nameがあること。
- icon-only controlは可視tooltipだけに依存せず、支援技術へ明確な名前を提供する。
- visible labelの文字列がaccessible nameへ含まれ、音声入力で表示名を使って操作できること。
- expanded、selected、pressed、checked、current、invalid、busy、disabled等のstateが必要な時に伝わること。
- decorationはaccessibility treeから除外し、focusable element自体へ`aria-hidden`を付けない。
- custom widgetは、採用したARIA patternのrole、property、keyboard interactionを部分的に実装しない。

## 6. Formと入力支援

- 各入力に永続的な可視labelを付け、placeholderだけをlabelにしない。
- `name`、`autocomplete`、`type`、`inputmode`を入力内容に合わせ、pasteやpassword managerを妨げない。
- hintとconstraintは入力前または入力中に確認でき、errorだけに情報を閉じない。
- validation errorは入力近くへ表示し、`aria-invalid`と`aria-describedby`等で対象と説明を結ぶ。
- submit前からactionを無効化して理由を隠すより、実行後に具体的な修正方法を示せるか検討する。
- 本当に利用不能なnative controlは`disabled`を使う。focus可能なまま説明を提供する場合は、pointer、keyboard、submitの挙動を同時に制御する。
- error後も入力済みdataを保持し、複数errorは全体と個別の両方から把握できること。

## 7. Dynamic contentとstatus message

- 保存完了、読み込み、件数更新、validation、通信失敗等が視覚的に分かること。
- controlに直接結びつくerrorは対象fieldと関連付け、routine updateは`status`等のpoliteな通知を使う。
- 緊急性のないtoastや件数更新をassertiveに読み上げない。緊急errorだけを割り込み通知とする。
- 同じmessageを繰り返す場合も通知されるよう、安定したlive regionと更新方法を対象支援技術で確認する。
- actionや重要errorを含むnotificationは、読む前に消えず、dismissまたは十分な到達手段を持つこと。
- loading stateでは対象領域、既存dataの扱い、完了後の変化が分かること。

## 8. Overlayと複合widget

- modalではbackgroundを操作・読み上げ対象から外し、focusを内部へ留め、close後に復帰する。
- menu、tabs、listbox、combobox、tree、gridは、採用したinteraction patternを明示し、keyboard操作とstateを一式で実装する。
- `aria-expanded`、`aria-controls`、active descendant、roving tabindex等は、実装方式に合わせて一貫させる。
- hoverやpointer位置だけで開くcontentは、focus、keyboard、touchでも到達でき、dismiss可能であること。

## 9. 見出し・landmark・構造

- pageと主要領域に内容を説明するheadingがあり、意味上の階層が追えること。
- heading levelを見た目のsize目的で選ばず、visual treatmentはCSSへ分離する。
- repeated navigationやchromeが本文より前にある場合、主要contentへ移動する手段を検討する。
- anchor先はsticky headerに隠れず、focus移動後に現在位置が分かること。
- table、list、definition、groupの関係がaccessibility treeにも現れること。

## 10. Image、icon、media

- decorative imageは空のalt、informative imageは目的に必要な情報、functional imageは操作結果を説明する。
- chartやdiagramは、画像説明だけでなく必要なdataまたは要点へ到達できること。
- autoplay、音声、video、animationはpause / stop手段を持ち、重要情報を時間制限だけで失わせない。
- iconの形や色だけに意味を依存せず、visible textまたはaccessible nameを提供する。

## 11. Contrastとforced colors

- 通常text、補助text、placeholder、link、icon、border、input、focus indicatorを、実際のforeground / background pairで測る。
- 通常textは4.5:1、大きいtextと必要な非text部品は3:1を最低目安とし、適用条件を確認する。
- hover、active、selected、disabled、error、dark mode等の各stateを個別に確認する。
- 色だけでerror、success、warning、selection、required、disabledを伝えない。
- forced colorsでoutline、control境界、selected state、icon、linkが消えないこと。system colorを無効化する場合は代替を確認する。

## 12. Target size

- Web上の操作対象は少なくとも24×24 CSS pxまたは同等の間隔・例外条件を最低目安とする。
- touch中心の文脈では44×44 CSS px程度を開始点とし、密度との両立を実際のtaskで判断する。
- 見た目を小さく保つ場合はpseudo-element等でhit areaを広げ、隣接領域と重ならないことを確認する。
- 小さいiconだけで危険操作を置かず、誤操作時の回復も用意する。

## 13. Zoom、reflow、text resize

- 200% zoomと320 CSS px相当で、主要taskに不要な横scroll、clip、overlap、到達不能を発生させない。
- text containerへ固定heightを置かず、文字拡大と長文でcontentやcontrolが欠落しないこと。
- viewport設定でuser zoomを制限しない。
- sticky / fixed要素、virtual keyboard、safe areaがcontentやfocusを隠さないこと。
- truncationで判断に必要な情報を失う場合は、全文へ到達する手段を用意する。

## 14. Motionと時間

- `prefers-reduced-motion`を尊重し、大きな移動、scale、parallax、autoplayを停止または穏やかな代替へ変える。
- motionを唯一のstate feedbackにせず、text、icon、形、色等の静的signalを併用する。
- actionやerrorを含むtime-limited contentは、停止、延長、dismiss、再確認ができること。
- flashing、rapid motion、scroll連動表現は、必要性と安全性を確認する。

## 15. 認知accessibility

- 画面目的、現在地、対象範囲、最初の行動が明確であること。
- 一貫した用語を使い、内部IDや実装用語を押し付けない。
- constraint、選択中state、過去入力を画面に出し、不要な記憶や推測を要求しない。
- errorを避け、起きた場合も原因、影響、修正方法、data保持を示す。
- 初心者向け説明は、熟練者の反復taskを恒常的に妨害しない。

## 16. P0例

- keyboardまたは支援技術で主要taskを完了できない。
- focusが見えない、失われる、overlayから抜けられない。
- interactive controlにaccessible nameがない。
- pointerでは可能だがkeyboardでは不可能なpathがある。
- error、selected、required等を色だけで伝える。
- textまたはcontrolのcontrastが最低基準を満たさない。
- 320 CSS pxまたは200%拡大で主要content / controlがclip、overlap、到達不能になる。
- reduced motion preferenceを無視する自動再生や大きなmotionによりtask継続が困難になる。
- 危険操作やdata lossの対象・影響・回復手段が伝わらない。

## 17. 検証

変更範囲に応じて次を組み合わせます。

- keyboard traversalとfocus移動・復帰。
- browser accessibility treeとaccessible name / role / state。
- axe-core等の自動検査。ただし自動検査だけで合格としない。
- 対象screen readerとbrowserでの読み上げ・操作。
- contrast測定、forced colors、dark mode。
- 200% zoom、320 CSS px、文字拡大、長文。
- reduced motion、notification時間、autoplay。
- 実行できない検証、その理由、残risk、次に必要な確認。
