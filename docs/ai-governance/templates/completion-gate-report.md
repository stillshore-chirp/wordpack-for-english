# 完了ゲート報告

## 判定

- 完了可否:
- 対象面: アプリ本体UI / GitHub共同作業面 / 混在 / N/A
- review route: UI変更レビュー / フロー監査 / 併用
- P0 / P1 / P2:
- 判定理由:

## 配送snapshotとgate ledger

### 現在のcheckpointとsnapshot

- current checkpoint:
- implementation snapshot（HEAD / base、変更path、入力閉包、条件）:
- measurement snapshot（HEAD / base、測定scope、条件）:
- publication snapshot（公開対象、安全性確認）:
- external delivery snapshot（CI、review / thread、mergeability）:

### stable evidence / volatile delivery state

- stable evidence（HEAD / base、path、関連設定、生成物、実行条件、結果、artifact参照）:
- volatile delivery state（CI、review / thread、mergeability、待機中status）:

### Gate ledger

| gate | checkpoint / snapshot（HEAD / base） | input closure（path / config / artifact / conditions） | stable evidence | volatile delivery state | result / artifact | invalidation reason / reacquire scope |
|---|---|---|---|---|---|---|
|  |  |  |  |  |  |  |

### 自己参照と計測

- self-reference検出結果:
- 検出時の分離gateまたは明示したmeasurement scope:
- report annotationをmeasurement evidenceへ混入させない扱い:

### 同条件 Before / After

change type、snapshot、runner、実行条件を固定して比較します。tokenは実telemetryを取得した場合だけ記録し、推定値は観測値として扱いません。

| phase | gate実行数 | wall-clock | status照会数 | output bytes | token telemetry（observed only） |
|---|---:|---:|---:|---:|---|
| Before |  |  |  |  |  |
| After |  |  |  |  |  |

### Review fixの扱い

- P0 / P1、security、secret、data integrity、受入証跡の矛盾によるblockingと対応:
- P2-only finding / 公開文言の調整、review予算、包括reviewを追加しない条件:
- fix後に入力閉包と交差して再取得したgate、その理由:

## 変更scope（UI変更レビューで差分がある場合）
<!-- agent-harness:uiux-completion-scope:start -->

| 項目 | 内容 |
|---|---|
| Target snapshot / ref |  |
| Base ref / SHA |  |
| Head ref / SHA |  |
| Commit / staged・unstaged diff |  |
| Diff identifier | `staged=<patch hash|empty>; unstaged=<patch hash|empty>; paths=<sorted changed path set>`。hash方式・取得時点も記録 |
| 追加側・削除側 |  |
| 変更意図（Issue / PR / commit） |  |
| Expanded surfaces | 直接consumer、parent、route、state、代表surface |
| Coverage / 未確認consumer / 除外理由 |  |
<!-- agent-harness:uiux-completion-scope:end -->

## 変更と影響

- 対象ユーザーと目的:
- 変更した画面・状態・文言・構造:
- 保持した既存挙動:
- 非対象:

## 対象面別証跡

### アプリ本体UI

- ユーザー価値:
- 初見理解:
- state matrix:
- accessibility:
- 視覚階層・copy:
- 熟練者効率:
- 満足感・信頼感:
- 反証レビュー:
- 変更前 / 変更後screenshot:

### GitHub共同作業面

- 文言・項目・順序・必須性:
- Markdown / form / YAML / frontmatter:
- link / preview:
- 公開安全性:

### UI変更レビュー（差分を伴う場合）

- 変更起因finding（Introduced / Regression）:

| 優先度 | Change status | Domain | 箇所 | 問題 | 修正状態 | 証跡 |
|---|---|---|---|---|---|---|
| P0/P1/P2 | Introduced / Regression |  |  |  |  |  |

- Pre-existing（今回の変更責任・変更起因件数から分離）:

| 優先度 | 箇所 | 観測事実・証跡 | 分離理由 | 完了判定への影響 | 別Issue / 後続 |
|---|---|---|---|---|---|
|  |  |  |  |  |  |

Pre-existingの通常の変更起因件数・責任は分離します。変更目的または安全性を阻害するP0/P1等のblocking findingは、完了可否と判定理由に残し、scopeと完了判断を明示的に見直します。別Issue化だけで完了扱いにしません。

### フロー監査（発動時）

- 対象タスク・取得手段・開始状態・完了状態:
- 重要ステップの順序付き証跡またはblocker:
- 操作中に観測した挙動・確認手段:
- findingとStep / screenshotの対応・証跡上の限界:
- 未確認範囲・残るリスク・次に必要な確認:

standaloneのフロー監査はdiff由来findingがないため、Change statusにN/A / 未分類（standalone）を記録し、Introduced / Regression / Pre-existingを必須にしません。UI変更レビューまたは併用では、各findingのChange statusをIntroduced / Regression / Pre-existingのいずれかで記録します。併用時は変更scope・変更起因findingとcurrent-runのstep証跡をこの同じ報告へ記録します。Pre-existingの通常の変更起因件数・責任は分離しますが、変更目的または安全性を阻害するP0/P1等のblocking findingは完了可否と判定理由に残し、別Issue化だけで完了扱いにしません。

## 検証

| 検証 | 結果 | 証跡 |
|---|---|---|
|  |  |  |

## PR / CI / Review

- latest commit:
- push CI:
- pull_request CI:
- latest meaningful changeへの自動・人間review:
- 未解決review thread:
- GitHub mergeability:
- review未提供（ソースコード変更では未完了blocker）:

## 未実行項目

| 項目 | 理由 | 残るリスク |
|---|---|---|
|  |  |  |

## 残るリスク・後続

| 優先度 | 内容 | 対応方針 |
|---|---|---|
|  |  |  |
