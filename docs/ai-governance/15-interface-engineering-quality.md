# インターフェース実装品質

この文書は、アプリ本体UIを実装・レビューする際に、レイアウト、タイポグラフィ、色とテーマ、アイコン、モーション、視覚的仕上げを再現可能な判断へ変換するための正本です。ユーザー価値、状態設計、アクセシビリティ、コピー、熟練者効率、信頼感は、それぞれの既存正本を優先します。

## 1. 適用原則

- 変更前に、使用中のframework、styling手段、component library、design token、対応viewport、theme、localization方針を確認する。
- 修正は既存の実装方式で行い、局所改善のためだけに第二のstyling方式や新しい依存を持ち込まない。
- 数値は、既存design system、対応環境、実測結果がない場合の開始点として扱う。文脈を無視して機械適用しない。
- sourceだけで確定できない見た目・折り返し・motion・contrastは、描画結果を確認する。確認できない場合は未確認として残す。
- 一つの根本原因が複数箇所へ波及する場合は、共有tokenまたはprimitiveに対する一件の指摘へ統合する。

## 2. レイアウトと適応性

### 構造とグルーピング

- 関連する情報と操作は、線を増やす前に余白、整列、背景面でまとまりを示す。
- 同じ階層の要素は共有する基準線へ揃え、偶発的なずれを残さない。
- 操作要素は静的な本文と区別でき、どの対象に作用するかが位置関係から分かること。
- 主情報、補助情報、主操作、副操作、危険操作の優先度を、位置、余白、文字、色、面の強さで一貫して表す。

### 狭幅・拡大・文字列伸長

- breakpointは端末名ではなく、内容が読み取れず操作できなくなる境界で決める。
- component単位で適応する場合は、既存環境が許す範囲でcontainer queryを検討する。
- 文字を含む領域へ固定heightを置かず、長い日本語、英数字、翻訳相当の伸長、200%拡大でも重要情報と操作を失わない。
- 320 CSS px相当の幅で、主要タスクに不要な横scroll、clip、overlap、到達不能な操作を発生させない。
- sticky / fixed要素はsafe area、virtual keyboard、zoom、scroll位置を考慮し、本文や主操作を隠さない。

### 方向性と順序

- 方向依存の余白・位置にはlogical propertyを優先し、RTLでも構造と操作順が成立するようにする。
- DOM順、視覚順、keyboard順、読み上げ順を意図的に一致させる。CSSによる見た目だけの並べ替えで意味を変えない。
- mixed-directionの識別子、数値、ユーザー入力は、必要に応じて`lang`、`dir`、`bdi`で境界を示す。

## 3. タイポグラフィ

### 読みやすさと階層

- 使用するfont family、weight、styleが実際に読み込まれ、browserの意図しない合成へ依存していないことを確認する。
- Web fontは対応browserに適した圧縮形式を使い、fallback時にも情報階層と強調が失われないようにする。
- font size、weight、line-heightは小さなsemantic scaleへ寄せ、用途のないone-off値を増やさない。
- 見出しは意味上の階層と視覚上の強さが矛盾せず、本文は実際のtypefaceと行長で連続して読めることを確認する。
- 長文は概ね60〜75文字相当を上限の目安とし、日本語では内容とfontに応じて読み返しにくい行長を避ける。

### 折り返しと動的値

- 見出し、説明、badge、table cell、URL、長い単語ごとに、wrap、overflow、省略の方針を定める。
- 省略した情報が判断に必要なら、tooltip、展開、詳細画面などで全文へ到達できるようにする。
- 件数、timer、価格、進捗など更新される数字は、layout shiftを防ぐためtabular numbersの適用を検討する。
- 入力欄はmobile browserで意図しない自動zoomを起こさない実文字サイズを確保する。見た目だけを小さくする場合も操作性とlayoutを実機相当で確認する。
- 自然な表記をdataとして保持し、見た目の大文字化などはCSSへ分離する。文字列連結で翻訳不能な文を作らない。

### 補助的な表示

- linkのunderline、selection、placeholder、caret、disabled風textも、通常状態と同様に識別可能であること。
- 読む、コピーする価値のあるtextは選択可能なままにする。drag等と実際に競合する局所だけを例外とする。
- `lang`を設定し、発音、改行、引用符、hyphenationが内容の言語に合うようにする。

## 4. 色とテーマ

- 生の色値を局所追加する前に、既存のsemantic tokenを利用する。役割が不足する場合は、値を借用せず新しい役割tokenを定義する。
- 同じ色へ複数の意味を持たせず、success、warning、error、selection、link、primary actionの役割を一貫させる。
- foreground / backgroundは実際に重なる描画pairでcontrastを測定し、透明度、gradient、image、hover、disabled、focusを含める。
- light / dark / increased contrast等のappearanceは、単純な反転ではなく、各状態・各pairを個別に確認する。
- 色だけで状態や意味を伝えず、text、icon、形、位置、border等を併用する。
- 一つの意思決定領域で、強い塗りを主操作へ集中させる。複数の色付き操作が競合する場合は優先度を見直す。
- 広色域や新しいcolor notationを使う場合は、対象browser、gamut外、fallbackを確認する。既存方式と混在させるだけの変更は避ける。

## 5. アイコンと視覚的仕上げ

- 同一surfaceでicon family、stroke weight、size、角の性格を揃え、隣接する文字との光学的な強さを合わせる。
- iconは`currentColor`等で状態を表し、active / disabledごとに別assetを増やさない。意味はaccessible nameまたは可視labelで保証する。
- 幾何学的な中央揃えが視覚的にずれるiconは、実際の描画を見て光学補正する。
- radius、border、shadow、surfaceの階層はtokenへ寄せ、入れ子の角やdepthが矛盾しないようにする。
- borderは構造・状態の区別に使い、depthだけが目的なら既存のelevation表現を使う。装飾を増やす前に情報構造を直す。
- hover、focus、active、selected、disabled、loading、success、errorの各状態で、反応が一貫し、情報が消えないことを確認する。

## 6. モーションと応答性

- motionは階層、状態遷移、因果関係を理解させる場合だけ使い、高頻度操作へ注意を奪うanimationを付けない。
- pointer操作中に状態が再変更されても追従できるtransitionを優先し、一度始まると割り込めない演出を常用しない。
- `transition: all`を避け、実際に変化するpropertyを限定する。layoutを毎frame再計算するmotionは、必要性と性能を確認する。
- `will-change`等の最適化hintは、計測で初動遅延を確認した箇所に限る。
- `prefers-reduced-motion`では、移動、拡大、parallax、autoplayを停止または穏やかな代替へ変える。motionだけを唯一のfeedbackにしない。
- 初回表示、enter、exit、hover、連続入力を低速再生または開発者toolで確認し、ちらつき、重複、遅延、意図しない初回animationを探す。

## 7. 優先度

### P0

- 320 CSS pxまたは200%拡大で、主要内容・操作がclip、overlap、到達不能になる。
- 必須textまたはcontrolのcontrastが最低基準を満たさない。
- 状態・意味を色またはmotionだけで伝える。
- motion preferenceを無視した自動再生・大きな移動により主要タスクを継続できない。
- 文字の省略、font fallback、theme不整合により、対象・結果・危険性を判断できない。

### P1

- hierarchy、wrap、density、theme、icon、state表現の不整合が、理解・操作・適応性を明確に損なう。
- 動的数字やloading stateのlayout shift、過剰motion、clipしやすい固定寸法が繰り返し発生する。
- 共有tokenまたはprimitiveの誤りが複数surfaceへ波及する。

### P2

- 利用者のtaskを妨げない局所的な光学補正、余白、radius、shadow、transitionの改善。
- 実測や利用状況を確認してから判断すべき追加のpolish仮説。

## 8. 検証証跡

変更に応じて次を記録します。

- 確認したviewport、zoom、文字列、appearance、RTL / LTR、state。
- font request、fallback、weight、wrap、動的値の観察結果。
- contrastのforeground / background pairと測定結果。
- keyboard、screen reader、reduced motion、forced colorsとの関係。
- animationの確認手順、性能測定、未確認項目。
- 問題箇所、現在状態、修正後の期待状態、利用者影響、P0/P1/P2。
