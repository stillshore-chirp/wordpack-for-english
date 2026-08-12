# UIコピーとマイクロコピー

UI copyは、ユーザーの理解、予測、安心、回復を支援する設計要素です。短さだけを目的にせず、利用者が対象、結果、state、影響、次のactionを正しく判断できることを優先します。

## 1. Recon

copyを追加・変更する前に確認します。

- 近くの画面で使われているproduct voiceと用語。
- 同じconcept、action、stateの既存label。
- localization catalogue、pluralization、変数補間の方式。
- sentence case等のcapitalization方針。
- error、危険操作、security、data loss等のhigh-stakesな文脈。

局所的な言い換えで既存用語を揺らさず、brand toneを残す場合も明確さ、翻訳可能性、stakesへの適合を優先します。

## 2. 基本原則

- ユーザーの言葉で書く。
- 抽象語、内部用語、実装都合の分類より、対象と結果を具体的に示す。
- 必要な情報を必要な場所へ置き、長い説明を読まないと操作できない設計にしない。
- action labelは実行後の結果を示す。
- errorは責めず、原因、影響、data保持、回復を示す。
- empty stateは現在のstateと次のactionを示す。
- 不安を煽らず、必要なriskを正確に伝える。
- 同じflow、同じconcept、同じstateには同じ語を使う。
- copyだけで解決できないinteraction problemは、interaction自体を見直す。

## 3. Voiceとtone

productのvoiceは一貫させ、toneをstakesに合わせます。

| 文脈 | Tone |
|---|---|
| onboarding、success、empty | 温かくてもよいが、意味を曖昧にしない |
| routine action、settings | 中立、簡潔 |
| error、destructive confirmation | 落ち着いて具体的。冗談、責任転嫁、過剰な感嘆を避ける |
| data loss、security、公開、課金、権限 | serious、明示的。対象、影響、回復可否を省略しない |

- instructionでは読み手へ直接伝え、抽象的な「ユーザーは」や責任主体をぼかす「私たちは」を乱用しない。
- 「簡単」「当然」等、できない人を責める含みを持つ語を使わない。
- 低stakesで既存brand characterがあり、理解と翻訳を損なわない場合は維持してよい。

## 4. Button

- verbから始め、何をするかを特定する。
- `OK`、`実行`、`はい`、`いいえ`だけでconsequenceを推測させない。
- destructive confirmationでは、confirmation buttonへ結果を繰り返す。
- 対象や件数が重要ならlabelまたは直前文脈で明示する。
- actionが長時間処理を開始する、外部送信する、公開する、課金する場合は、必要な影響を実行前に示す。
- loading中も元のactionが分かるlabelを保ち、spinnerだけへ置き換えない。

例:

- 弱い: `実行`
- 良い: `選択した3件を削除`

- 弱い: `送信`
- 良い: `レビュー依頼を送信`

## 5. Link

- link textだけを読んでも、移動先または得られる情報が分かること。
- `こちら`、`click here`、同一画面に複数あるbare `詳しく見る`を避ける。
- actionとnavigationを文言・elementの両方で区別する。
- deviceを限定する必要がなければ、`click`や`tap`より`選択`等の中立語を使う。
- 外部site、download、新しいtab等、予測に必要な差がある場合は示す。

## 6. Flow vocabulary

- multi-step flowでは、開始、前進、完了、cancel、戻るの語を一貫させる。
- `次へ`と`続ける`等のsynonymを意味なく交互に使わない。
- stepごとにactionの結果が変わる場合は、genericな前進語より具体的なverbを使う。
- final actionは、保存、送信、公開、作成等の結果を明確にする。
- title、heading、button、success messageで同じ対象を異なる名前にしない。

## 7. Settingとtoggle

- toggle labelはONの時に成立するstateを表す。
- negative labelとtoggle stateを組み合わせたdouble negativeを避ける。
- setting名だけでは影響が分からない場合、短い説明を近くに置く。
- 参照する別settingがある場合は、そのsettingへのlinkを提供し、長いnavigation手順を文で説明しない。
- immediate saveか、別のsave actionが必要か、反映時期はいつかを分かるようにする。

## 8. Form、label、placeholder、hint

- fieldには永続的な可視labelを置き、placeholderをlabelにしない。
- placeholderはformatや具体例に使い、入力開始後に消えても困らない情報だけを置く。
- constraintとformatはerror発生前または入力中に確認できるようにする。
- required / optionalの表記方針をform内で一貫させる。
- helper text、error、counter、statusがどのfieldへ属するか分かるようにする。
- labelとaccessible nameが矛盾しないこと。

## 9. Error

errorは診断名ではなく、回復のためのinstructionです。必要な範囲で次を含めます。

- 何が起きたか。
- どの対象・操作に影響するか。
- 原因または修正条件。
- 入力・作業dataが保持されているか。
- 次にできるaction。
- retry、戻る、保存、問い合わせ、詳細確認等の導線。

悪い例:

```txt
エラーが発生しました。
```

良い例:

```txt
保存できませんでした。接続を確認して、もう一度保存してください。入力内容は保持されています。
```

- `Oops`等のplayfulな表現、感嘆符、user blameをhigh-stakes errorで使わない。
- field errorは対象fieldの近くに置き、global messageだけで探させない。
- validation conditionは肯定形で、修正方法が分かるようにする。
- 同じerrorが多数発生する場合は、copy変更だけでなくinteractionやdefaultを見直す。

## 10. Empty、no-results、permission、unavailable

状態を一つの`データがありません`へ潰しません。

### 初回empty

- 何を置く場所か。
- 現在なぜ空か。
- 最初の一件を作るaction。
- sampleや説明が必要か。

### No-results / filter-empty

- queryやfilter condition。
- search scope。
- conditionをclear / relaxするaction。
- spelling、表記揺れ、condition過多を示す必要があるか。

### Permission denied

- 何の権限が不足しているか。
- 誰へ依頼するか、どこで設定するか。
- security上見せてはいけない情報を漏らしていないか。

### Unavailable / maintenance / offline

- 一時的か、user actionで回復可能か。
- retry、代替task、後で再開する方法。
- 入力や未保存dataの扱い。

## 11. Disabled

- 押せない理由と有効化条件が分かること。
- hoverしかできないtooltipに理由を閉じない。
- disabledにすることでactionの存在や修正方法を隠していないか確認する。
- 実行後に具体的なvalidationを示す方が理解しやすい場合は、actionを早期にdisabledにしない。
- loading中の一時disabledと、permission / prerequisiteによる利用不能を同じ文言へしない。

## 12. Successとstatus

- 何が完了したか。
- どのdataが保存、送信、公開、削除、更新されたか。
- 次にできるaction。
- undoやdetail確認が必要か。
- background処理が続く場合、完了と受付を混同しない。
- notificationが消える場合も、重要な結果へ再到達できること。
- 件数更新やroutine statusは簡潔にし、同じ情報を複数箇所で競合させない。

## 13. 危険操作・公開・送信・課金・権限

実行前に、必要な範囲で次を明確にします。

- 対象名、件数、scope。
- 実行後に起きること。
- 取り消し・復元可否。
- 他者への公開・通知・送信。
- 課金額、頻度、開始時期。
- 権限変更後に可能になる操作。
- 個人情報・dataの共有範囲。

confirmationはconsequenceを具体化し、曖昧な安心表現や必要以上に恐怖を煽る表現を避けます。

## 14. Localizationと変数

- 文を固定語順の断片連結で作らず、languageごとの完全なtemplateとして管理する。
- countはpluralization方式へ接続する。
- date、time、number、currency、unitをlocaleに合わせる。
- translated stringの伸長でbutton、heading、table、notificationがclipしないこと。
- idiom、pun、culture依存のhumor、不要なgenderを避ける。
- user-generated text、identifier、mixed-direction contentの境界を明確にする。
- dataとして自然なcaseを保持し、uppercase等のpresentationはCSSへ分ける。

## 15. 一貫性

- 同じconceptに同じ名前を使う。
- 同じactionに同じverbを使う。
- `作成`、`保存`、`送信`、`公開`、`適用`等の結果を混同しない。
- 日本語と英語の混在を、product内で必要な固有名・標準名に限定する。
- heading、button、menu、toast等のcapitalizationとpunctuationを揃える。
- backend error codeや内部IDを、そのままuser-facing copyにしない。

## 16. P0

- action、対象、scope、consequenceが分からず、誤操作・data loss・誤送信・誤公開につながる。
- errorに回復方法がなく、主要taskを継続できない。
- permission、empty、error、loadingを誤認させる。
- destructive、課金、公開、権限、個人情報で対象・影響・取り消し可否が不明。
- visible labelとaccessible nameが矛盾し、操作対象を正しく指定できない。
- copyがuserを責める、または実際より安全に見せる。

## 17. P1

- 用語、flow vocabulary、capitalizationの揺れが理解を明確に遅らせる。
- empty、success、disabled、errorの次actionが弱いが回避可能。
- 長い説明、抽象label、内部用語が反復taskや初見理解を損なう。
- localization、pluralization、文字列伸長の問題が代表stateで発生する。

## 18. Evidence

- current copyと完全なreplacementを示す。
- screen、component、state、`path:line`を示す。
- flow全体で用語とactionを確認する。
- variable interpolation、pluralization、long string、narrow widthを確認する。
- accessibility nameとの一致を確認する。
- 実ユーザーから得ていない反応を事実として書かない。
- 変更差分reviewではIntroduced / Regression / Pre-existingを`16-change-scoped-interface-review.md`に従って分ける。
