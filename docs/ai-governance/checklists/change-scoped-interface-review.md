# 変更差分インターフェースレビューチェックリスト

## Scope

- [ ] targetをworking tree / branch / range / PRとして明示した。
- [ ] base ref / SHAとhead ref / SHAを確定した。
- [ ] branchのcommit差分とstaged / unstaged差分を取りこぼしていない。
- [ ] 差分がない時に、直前commitへ勝手に切り替えていない。
- [ ] lockfile、generated、snapshot、vendor、binary等の除外と理由を記録した。
- [ ] Issue、PR本文、commit messageから変更意図と受け入れ条件を確認した。

## Affected surfaces

- [ ] 変更fileが描画・利用されるroute、parent、consumerを確認した。
- [ ] shared primitive、design token、theme変更は代表surfaceへ展開した。
- [ ] backend / schema / translation変更が利用者stateへ与える影響を確認した。
- [ ] 確認したconsumer数と未確認範囲を記録した。

## Diff

- [ ] diffの追加側と削除側を同じ重さで読んだ。
- [ ] accessible name、focus、keyboard、status、recoveryの削除を確認した。
- [ ] responsive、wrap、RTL、theme、reduced motionの削除を確認した。
- [ ] copy、scope、結果、危険性、入力保持、近道の削除を確認した。
- [ ] 等価な代替実装があるsignalを回帰として誤報していない。

## Classification

- [ ] 各findingをIntroduced / Regressionへ分類した。
- [ ] base側の証跡でRegressionを確認した。
- [ ] Pre-existingを今回の責任・finding件数・判定から分離した。
- [ ] 同じroot causeを一件へ統合し、影響箇所を列挙した。

## Completeness

- [ ] 新しいvariant、theme、size、stateが全interaction stateで成立する。
- [ ] 新しいcomponentがempty、error、narrow、long-contentへ対応する。
- [ ] user-facing textが既存localizationと用語へ接続される。
- [ ] sibling surface、test、story、UserManual、state matrixの更新要否を確認した。
- [ ] Issueにない改善をscope creepとして押し付けず、目的達成に不可欠な欠落と分けた。

## Evidence・verdict

- [ ] findingにpriority、domain、change status、location、current、expected、user impact、evidenceがある。
- [ ] sourceだけで確定できないvisual/runtime claimを描画確認またはNot verifiedにした。
- [ ] domain別coverageと「変更差分に確認対象なし」を区別した。
- [ ] 実行command、描画・操作確認、未実行検証、残riskを記録した。
- [ ] Pass / FailはIntroducedとRegressionを対象に判定した。
- [ ] review-only依頼でworking treeを変更していない。
