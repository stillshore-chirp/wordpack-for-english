---
name: github-delivery
description: "大小を問わないすべてのソースコード変更と、Issue、branch、commit、push、PR、CI、review、release準備を安全に一気通貫で行う時に使う。利用可能なGitHub clientを使い、latest headの検証、コードレビュー、mergeabilityを確認し、merge/closeは別の明示指示がある場合だけ行う。"
---

# GitHub配送 Skill

## 発動条件

製品コード、test、script、workflow、schema、挙動を変える設定の追加・変更・削除では、大小を問わず必ず発動します。ソースコード変更依頼は、IssueからGitHub上のマージ可能状態まで通常配送する依頼を兼ねます。read-only調査や回答だけでは発動しません。

## 1. 開始前

- ルート `AGENTS.md` と変更対象に最も近い `AGENTS.md` を読む。
- 現在のdefault branch、作業branch、未commit差分、直近履歴を確認する。
- 無関係な差分の所有者と範囲を確認し、巻き込まない。
- ソースコード編集前に主Issueと専用branchを確定する。detached HEADでは編集せず、既存PRを継続する場合はIssue・branch・PRが同じ作業を指していることを確認する。
- GitHub CLI、GitHub API、connectorなど、利用可能で認証済みのclientを使う。一つのclientが使えなくても、同等のclientで完了ゲートを満たせる場合は作業を止めない。

## 2. Issue

- 既存Issueを検索し、依頼を完全に含むものがあれば使う。
- ソースコード変更は規模や種類にかかわらず主Issueを必須とし、既存Issueがなければ編集前に作成する。同一PR内のreview修正は、そのPRの主Issueを継続して使う。
- ソースコードを含まない文書やメタデータだけの軽微な変更でIssueを省略する場合は、PR本文へ短い理由を書く。
- [`docs/ai-governance/14-issue-quality-gate.md`](../../../docs/ai-governance/14-issue-quality-gate.md)に従い、理由、根拠、現在と目標、範囲、非対象、受け入れ条件、検証、リスクを書く。

## 3. Branch、実装、commit

- default branchの最新状態から作業branchを作る。標準名は `agent/<purpose>` とし、既存branchやユーザー指定がある場合はそれを尊重する。
- 複数工程でも、真のblockerがない限り調査、実装、検証、配送まで継続する。
- 実装前に、受け入れ条件と依存関係から予定commitの責務、関連test・文書、実装順序を決める。責務の境界が実装中に変わった場合は、次の編集前に計画を更新する。
- commitは独立してreview・revertできる一つの論理的責務または受け入れ条件の単位にする。関連するtest、文書、schema・client等の生成物は同じcommitへ含める。
- 一つの責務の実装・関連test・文書・検証が完了したら、次の独立責務を編集する前にstage確認とcommitを完了する。複数責務を共有作業ツリーへ蓄積し、最後に全差分を再読して後付け分解しない。
- サブエージェントの完了報告を受けたら、メインが担当fileと差分をreviewし、その責務だけを上記の時点でcommitへ回収する。他担当の未完了差分はstageしない。
- 作業時間、行数、担当者だけを理由にcommitを分割または一括化しない。
- `git add .`と`git add -A`を使わず、stage対象のpathを明示する。commit前にstaged file名、staged diff、`git diff --check`、secret・実データ・無関係差分の不在を確認する。
- commit messageは変更の責務を短く表す日本語にする。
- ソースコード変更依頼はcommit、push、非ドラフトPR作成・更新、CI再実行、reviewへの返信・修正、対応済みthreadの解決までを許可する。これらの通常配送について追加の包括確認を求めない。

## 4. PR

- ソースコード変更では非ドラフトPRを作成または更新し、GitHub上の完了ゲートまで継続する。
- 主Issueは1つに絞る。完全解決は`Closes #123`、部分対応は`Refs #123`を使う。
- PR本文には、変更内容、保持した挙動、検証、未実行項目、対象面の証跡、公開安全性、残るリスクを書く。
- UI変更ではUI/UX Skill、公開物では公開安全性Skillの成果を反映する。

## 5. CIとreview

- latest headに紐づき、対象branchで定義されたpush / pull_request等のCIを確認する。失敗時はログから原因を特定し、修正、commit、push、再確認する。
- CI成功後、GitHub上で確認可能な自動または人間のコードレビュー、review thread、review commentをlatest headで確認する。
- actionableな指摘はまとめて修正し、変更後のheadでCIと該当reviewを再確認する。
- latest meaningful changeに対するclean reviewが1回得られ、actionableな未解決threadがなく、GitHubのmergeabilityがcleanで、CIと必須条件を満たせばreviewを終了する。
- 変更のないheadでclean結果を増やすためだけの再レビューを行わない。
- ソースコード変更でコードレビューが提供されない場合、自己レビューは補助証跡に限り、完了条件の代替にしない。未完了のblockerとして報告する。

## 6. 権限境界と終了

- merge、Issue / PRのclose、release、production deploy、破壊的変更は、対象を特定した別の明示指示がある場合だけ行う。
- blocker報告には、失敗しているcheckまたは操作、証跡、試した対応、未完了範囲、次の最短アクションを含める。
- 最終報告には、Issue、branch、commit、PR、local verification、CI、review、remaining risksのうち今回に関係するものを示す。
