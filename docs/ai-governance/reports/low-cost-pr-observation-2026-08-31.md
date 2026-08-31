# #656 低コストPR観測ベースライン 2026-08-31

## 問いと範囲

#653〜#655の低コスト改善後に、通常PRのwall-clock、CI check選択、Playwright選択、rerunの明白な構造変化があるかを、既存の公開GitHub証跡だけで確認する。測定専用PR、同一HEADの再実行、常設telemetry・workflow・job・runtimeは対象外とする。

対象7件はすべて#655のclose前に完了した公開PRであり、#655 close前のbaseline/transitionとして扱う。#655 close後の自然発生PRは0件であるため、post-#655 regressionの結論は出せず、#656は未完了とする。調査専用のtelemetry、workflow、job、runtimeは追加・実行・収集していない。

## Source / snapshot

公開sourceは [PR #645](https://github.com/stillshore-chirp/wordpack-for-english/pull/645)、[#647](https://github.com/stillshore-chirp/wordpack-for-english/pull/647)、[#648](https://github.com/stillshore-chirp/wordpack-for-english/pull/648)、[#650](https://github.com/stillshore-chirp/wordpack-for-english/pull/650)、[#659](https://github.com/stillshore-chirp/wordpack-for-english/pull/659)、[#660](https://github.com/stillshore-chirp/wordpack-for-english/pull/660)、[#661](https://github.com/stillshore-chirp/wordpack-for-english/pull/661)、および [Issue #655](https://github.com/stillshore-chirp/wordpack-for-english/issues/655) とした。対象snapshotは`canonical/main`=`d765021`、確認日は2026-08-31 JST。GitHub APIの`*_at`はUTCとしてイベント順を判定し、本文ではJSTの日付粒度だけを示して秒単位時刻を掲載しない。

再現用のquery outlineは、PRの`number/state/baseRefName/headRefOid/mergedAt/statusCheckRollup`、Actions runの`name/head_sha/run_started_at/run_attempt`、check runの`name/conclusion/completed_at`、Issue timelineの`event/created_at/source`を読むものとする。認証情報とraw logは取得・転載せず、run/job IDと秒単位のtimestampは本報告へ掲載しない。

## Data-quality gate

- 7件はいずれも`main`へmerge済みで、各headの公開CI runはattempt 1、rerun 0。check rollupは各13件で、failureはない。
- #653、#654、#655はclosed（[Issue #653](https://github.com/stillshore-chirp/wordpack-for-english/issues/653)、[#654](https://github.com/stillshore-chirp/wordpack-for-english/issues/654)、[#655](https://github.com/stillshore-chirp/wordpack-for-english/issues/655)）。#656はopen（[Issue #656](https://github.com/stillshore-chirp/wordpack-for-english/issues/656)）。
- #655 timelineのclose eventより前に7件のmerge eventが完了していることを公開event順で確認した。#659〜#661は近接したtransition期間の行として、post-changeの自然観測と混同しない。

## Metric formulas

- `workflow_to_quality_seconds` = `Quality gate completed_at - CI run_started_at`。同じPR headのCI workflowとcheckを対応付けた経過秒である。
- `pr_created_to_quality_seconds` = `Quality gate completed_at - PR createdAt`。PR作成時点を起点とする単一の定義であり、`updatedAt`は使わない。latest-head push timestamp起点のvariantは収集しておらず未確認であり、本報告はIssueで許可されたPR-created originを一貫して用い、`workflow_to_quality_seconds`はtrigger後のfinal-head CIだけを切り出す。
- `success/skip/failure` = PRの公開`statusCheckRollup`を`conclusion`別に数えた件数。
- `attempts/reruns` = CI workflowのattempt数 / `attempts - 1`。今回は全行`1/0`。
- `Playwright smoke / visual` = `Playwright smoke (selected flows)` / `Playwright visual regression`の公開結論を、successは`selected`、skippedは`skip`へ正規化したもの。これは対象spec数の推定ではない。

## Baseline table

| PR | category | workflow_to_quality_seconds | pr_created_to_quality_seconds | success/skip/failure | attempts/reruns | Playwright smoke / visual |
|---|---|---:|---:|---:|---:|---|
| [#645](https://github.com/stillshore-chirp/wordpack-for-english/pull/645) | governance | 156 | 1580 | 11/2/0 | 1/0 | selected/selected |
| [#647](https://github.com/stillshore-chirp/wordpack-for-english/pull/647) | governance/delivery | 26 | 861 | 5/8/0 | 1/0 | skip/skip |
| [#648](https://github.com/stillshore-chirp/wordpack-for-english/pull/648) | workflow/security | 178 | 182 | 11/2/0 | 1/0 | selected/selected |
| [#650](https://github.com/stillshore-chirp/wordpack-for-english/pull/650) | governance/validator | 159 | 163 | 11/2/0 | 1/0 | selected/selected |
| [#659](https://github.com/stillshore-chirp/wordpack-for-english/pull/659) | governance/monitor | 33 | 36 | 4/9/0 | 1/0 | skip/skip |
| [#660](https://github.com/stillshore-chirp/wordpack-for-english/pull/660) | workflow/E2E | 166 | 169 | 11/2/0 | 1/0 | selected/selected |
| [#661](https://github.com/stillshore-chirp/wordpack-for-english/pull/661) | environment/cleanup | 167 | 170 | 6/7/0 | 1/0 | skip/skip |

## 観測と計算

workflow-origin の合計は885、平均は約126.4、中央値は159、範囲は26〜178。PR-origin の合計は3161、平均は約451.6、中央値は170、範囲は36〜1580である。PR-originはPR作成からのレビュー／修正時間を含み、workflow-originは最終headのCI開始から品質ゲート完了までを切り出す。どちらも単独では因果を証明しない。check rollupの合計はsuccess 59、skip 32、failure 0（91件）。短い#647/#659はskipが8/9件で、選択checkの多い行より短いが、7件のbaselineから因果や恒常傾向は推定しない。Playwrightはselected/selectedが4件、skip/skipが3件、rerunは全件0である。

## 推論と推奨

このsnapshotから、#653〜#655導入後の回帰は判定できない。#656は未完了のまま、#655 close後に自然発生した5〜10件以内の通常PRが得られた時点で同じ公開fieldを再取得し、baseline/transitionとpost-changeを分離して比較する。品質・security・authorization・production-safety gateは保持し、速度目的のskip・降格やproxy metricの導入は行わない。

## Unknowns / 残るリスク

targeted spec数、出力（件数・bytes）、agent handoff、実token、runtime cleanup incident、runner内部待機・cache要因は、今回の公開証跡では比較可能な値がないためunknownとする。checkのskip件数や経過秒を、これらのproxyとして扱わない。公開metadataはcheckの状態を示すが、実行内容の完全性、認可挙動、runtime resourceの残留を証明しない。
