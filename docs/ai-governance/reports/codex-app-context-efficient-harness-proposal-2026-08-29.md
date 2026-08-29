# Codexアプリ改善提案: lane状態と証跡再利用 2026-08-29

## 文書の位置付け

- 対象Issue: #628
- 種別: Codexアプリ側の改善提案。repositoryの共有正本へアプリ固有の挙動を追加する文書ではない。
- 目的: tool-neutralなlane契約で、依存関係、snapshot、runtime resource、証跡の再利用条件を表現し、Codexアプリ側のcompactな状態表示と待機経路へ接続できるようにする。
- 状態: proposal / app runtime未確認。fixtureやrepository文書だけでCodexアプリの実挙動を証明しない。

## 根拠と確度

| 区分 | 内容 |
|---|---|
| 公開確認済み | `origin/main` の共有正本はlane、evidence package、input closure、snapshot、invalidation、bounded outputを定義している。 |
| Issueで提示された判断材料 | timeout後の固定間隔照会、完了laneの長文再取得、runtime resource所有の不明確さ、Codexアプリ固有のcompact statusとcommentary cadenceを分離して再検証する。 |
| 未確認 | Codexアプリの実装、`list_agents` の実出力、実際のstatus query回数、commentaryの発火条件、アプリAPIの互換性。これらはアプリ側の再現とtrusted runtime smokeで確認する。 |

## 共有正本への参照

canonical lane schema、evidence package、snapshot phase、待機・再照会、direct-primary exceptionは [`docs/agent-harness.md`](../../agent-harness.md) を唯一の正本とする。この提案ではfield定義や汎用待機手順を再掲せず、Codexアプリ側の未実装surfaceとの接続課題だけを扱う。app-onlyの`list_agents` compact表示とcommentary cadenceは共有契約へ擬似実装しない。

## Codexアプリ側の専用改善提案

### 再現手順と確認状態

再現は公開安全なfixtureまたは許可された実行環境で、child laneを1つだけ対象に行う。

1. laneがtimeoutになり、new signalがない状態を作る。
2. timeout直後の待機経路、status query、progress commentaryの発火を時系列で記録する。
3. laneを完了させ、完了後に長文結果が再取得されるか、bounded packageとartifact referenceだけが返るかを確認する。
4. 同一snapshot / input closureで再度gateを要求し、既存evidenceが再利用されるかを確認する。

このrepositoryからはCodexアプリbinaryやapp-only APIを実行できないため、上記の実行結果は未確認である。実行時も実ユーザー入力、認証情報、trace / request / job identifierを収集・公開しない。

### 期待仕様

- app status surfaceはactive laneだけを対象にし、lane状態、`snapshot_phase`、`last_activity`、phase、`expected signal`、compactな`progress_revision`、依存状態、resource / portの所有要約、cleanup状態、`output_cap`、evidence / artifact referenceをboundedに返す。completed laneをstatus listへ再掲しない。
- `progress_revision`を指定するevent-driven waitを使い、timeout後はbackoff re-waitを予約する。new signalまたはdiagnostic reasonがない限り同じstatus queryを発行しない。
- progress commentaryはstatus queryと独立し、cadenceのためだけに同一状態を再取得しない。
- 完了laneはfinal outputを自動再送せず、final outputなしのcompactな`terminal receipt`とbounded evidence package、artifact referenceだけを返す。
- `list_agents` のcompact表示形式はこのapp-only proposalの対象とし、共有正本の必須APIや他toolの共通挙動にしない。

### 実挙動と影響

現時点で実挙動は未確認であり、repository上の契約から推定してはいけない。Issueで提示された問題が再現した場合、primaryのcontext消費、同一証跡の重複取得、runtime resourceの解放漏れ、完了判断の遅延が発生し得る。影響は開発・運用の効率と証跡の信頼性に限定して評価し、WordPack製品の利用者影響とは分けて記録する。

### 必要なapp API変更（提案）

既存APIの名称やversionを断定せず、次の意味を満たすapp-side surfaceを設計する。

- bounded lane status read model: 共有正本の状態要約と`artifact_reference`をboundedに返す。
- wait / notification contract: timeout、backoff、new signal、diagnostic reasonを区別し、待機中の再照会を抑止する。
- progress event contract: commentaryをstatus queryから分離し、`new signal`の有無を明示する。
- evidence reuse contract: 共有正本のsnapshot、input closure、`invalidation_condition`を参照する。
- resource lifecycle contract: resource、port、cleanupのownerと完了状態を返す。

追加のapp-only API候補は、未実装のrevision指定event-driven wait、active-only status read、`last_activity` / phase / `expected signal`を含むcompact progress event、final outputを持たないterminal receiptです。これらはCodexアプリ側の改善提案であり、repositoryの実装済み契約やruntime enforcementの証拠として扱いません。

これらはCodexアプリの改善候補であり、repositoryの共有正本へ`list_agents`、特定SDK、特定CLI、アプリ内部イベント名を持ち込む変更ではない。

## 検証と完了条件

- app contract検証: bounded status、wait / notification、progress event、completion response、evidence reuseのapp-side接続をdeterministic fixtureで確認する。
- runtime smoke: fixtureのpassはruntime enforcementの証拠にせず、アプリ実行で発火したeventと未発火eventを別々に記録する。
- evidence check: 同一snapshot / input closure / conditionsの成功gateが再実行されず、path変更時だけ対象evidenceが失効することを確認する。
- 公開安全性: 文書、artifact reference、実行要約にsecret、個人情報、local path、本番識別子、raw log、追跡可能な実値がないことを確認する。

アプリ側の再現、API互換性、実runtimeのcommentary cadence、実際の`list_agents`出力は、この提案だけでは完了扱いにしない。
