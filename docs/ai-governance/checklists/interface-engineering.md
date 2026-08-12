# インターフェース実装品質チェックリスト

## Recon

- [ ] framework、styling方式、component library、design token、theme、対応viewportを確認した。
- [ ] 既存の実装方式で修正し、局所改善のためだけに新しい依存や第二のstyling方式を追加していない。
- [ ] sourceだけで確定できない見た目・折り返し・motion・contrastを描画結果で確認した。

## Layout・adaptation

- [ ] 関連要素のgrouping、基準線、主操作・副操作の優先度が一貫している。
- [ ] breakpointを内容が破綻する境界から決めている。
- [ ] 320 CSS px、200%拡大、長文、大量dataで主要contentとcontrolがclip・overlap・到達不能にならない。
- [ ] text containerへ不適切な固定heightを置いていない。
- [ ] logical property、RTL、DOM順・視覚順・keyboard順を確認した。
- [ ] sticky / fixed要素がsafe area、virtual keyboard、focus、contentを隠さない。

## Typography

- [ ] 実際に使用するfont family、weight、style、fallbackを確認した。
- [ ] font size、weight、line-heightがsemantic scaleへ寄っている。
- [ ] 見出し階層、本文の行長、折り返しを実contentで確認した。
- [ ] URL、長い英数字、badge、table cellのoverflow方針がある。
- [ ] 省略された重要情報へ全文確認手段がある。
- [ ] 更新される数字にtabular numbersが必要か確認した。
- [ ] mobile inputで意図しないauto zoomを起こさない。
- [ ] `lang`、mixed-direction、text selectionを確認した。

## Color・theme

- [ ] 既存semantic tokenを使用し、生の色値を局所追加していない。
- [ ] 一つの色へ複数の意味を持たせていない。
- [ ] foreground / backgroundの実際の描画pairでcontrastを測定した。
- [ ] light / dark / increased contrastの各stateを確認した。
- [ ] 色だけでstateや意味を伝えていない。
- [ ] 主操作の強調が他の色付きcontrolと競合していない。
- [ ] 広色域・新しいcolor notationを使う場合のgamutとfallbackを確認した。

## Icon・visual finish

- [ ] icon family、stroke、size、文字との光学的強さが一貫している。
- [ ] icon-only controlの意味が可視labelまたはaccessible nameで保証されている。
- [ ] radius、border、shadow、surfaceの階層がtokenと一致している。
- [ ] hover、focus、active、selected、disabled、loading、success、errorを確認した。
- [ ] 装飾追加で情報構造の問題を隠していない。

## Motion・performance

- [ ] motionが状態・階層・因果関係の理解に役立つ。
- [ ] 高頻度操作へ不要なanimationを付けていない。
- [ ] `transition: all`を使わず、変化propertyを限定している。
- [ ] `prefers-reduced-motion`で大きな移動、scale、parallax、autoplayを停止または代替している。
- [ ] motion以外の静的feedbackがある。
- [ ] layout再計算、初動遅延、ちらつき、意図しない初回animationを確認した。

## Evidence

- [ ] viewport、zoom、appearance、direction、state、content条件を記録した。
- [ ] contrast、font、wrap、dynamic value、motionの確認結果を記録した。
- [ ] 未確認項目、理由、残risk、次に必要な確認を記録した。
