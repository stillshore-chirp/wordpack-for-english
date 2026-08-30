# Agent Principles

この文書は、WordPack for Englishの設計・実装判断に使う heuristic だけを定めます。hard gateと権限境界は [`AGENTS.md`](../AGENTS.md)、委任・証跡・task-stateは [`docs/agent-harness.md`](agent-harness.md)、作業手順は該当Skillを優先します。

複数の原則が競合する場合は、要件、既存構造、変更容易性、誤用リスク、検証可能性を比較します。数値目安だけでFailにせず、読み手と変更者が安全に扱えるかで判断します。

## KISSとYAGNI

- 要件を満たす最小の構造から始め、使われない拡張点や設定を先行追加しません。
- ネスト、間接参照、動的import、メタプログラミングは、単純な構造より明確な利点がある場合に使います。
- 将来可能性だけを理由にinterface、factory、plugin、汎用DSLを増やしません。
- セキュリティ、可観測性、エラー処理、data integrityに必要な備えは、利用前でも追加できます。

## DRYと共通化

- 重複回数だけで抽象化を強制しません。
- 変更理由、lifecycle、契約が同じ重複は共通化を検討します。
- 偶然似ている処理や、今後別方向に変わる処理は分けて保ちます。
- 共通化で呼び出し側の意図が隠れる場合は、明示的な重複を許容します。
- 定数、schema、validation、test dataは、不整合を防げる単位へ集約します。

## SRP、SoC、依存方向

- file、class、function、componentの責務を、名前とpublic APIから説明できる状態にします。
- UI / Presentation、Application、Domain、Infrastructureを区別し、外部技術の詳細をdomain判断へ漏らしません。
- logging、metrics、retry、authorizationなどの横断的関心は、一貫して適用できる境界へ置きます。
- component内の取得、状態、描画、業務判断を分ける価値と、分割による追跡コストを比較します。
- 分割は行数ではなく、独立して変更・検証できる責務の境界で判断します。

## OCPと外部統合

- 種別追加のたびに広範囲の条件分岐を変更する構造では、strategy、registry、polymorphismを検討します。
- 外部API、storage、payment、LLM providerの抽象化は、差し替え、契約test、障害分離に実益がある境界へ置きます。
- 一つの実装しかなく、差し替え需要もない場合は、interface追加を目的化しません。
- 既存の公開契約を変える場合は、互換性、migration、versioning、rollbackを検討します。

## POLAと可読性

- 同種のAPI、非同期処理、error、validation messageは一貫した契約にします。
- 副作用や破壊的操作は、名前、引数、戻り値から予測できるようにします。
- 略語や内部用語は一般性があるものに限り、利用者向けUIへ実装用語を出しません。
- コメントは処理内容の逐語説明でなく、コードから分からない理由、制約、契約を補います。
- 新規参加者が安全な変更箇所と検証方法を判断できる情報を残します。

## エラー処理と可観測性

- errorを消すこと自体を目的にせず、根本原因と利用者影響を特定します。
- 想定可能な失敗は、retry、fallback、停止、user通知の方針を明示します。
- fallbackでdata integrityや設定不備を隠しません。
- logは構造化し、level、event、必要最小限のcontextを持たせます。
- 主要use caseでは、成功率、latency、retry、failure categoryを観測できる設計を検討します。

## テスト

- Unit Testを判断logic、Integration Testを境界契約、E2Eをcritical導線へ使います。
- 時刻、乱数、network、外部API、port、DB namespaceなどの非決定要素を制御します。
- UI testはrole、label、visible text、状態変化を優先し、CSS classや偶然のDOM構造へ結合しません。
- APIのrequest、response、status、error形式が変わる場合はcontract testで固定します。
- bug修正では、修正前に失敗する条件と期待結果を回帰testへ残します。
- coverage値は未検査領域を探す信号として使い、数字だけを目的化しません。
- flaky testは再実行で隠さず、待機条件、競合、非同期、環境差の原因を直します。

## ファイルと依存

- fileが大きくなった場合は、責務、変更理由、test境界に沿った分割を検討します。
- 依存は最小限に保ち、標準機能や既存依存で十分な場合は追加しません。
- lock fileを依存変更へ追従させ、生成物、環境依存file、credentialを追跡しません。
- 設定は環境ごとの差を明示し、secret managementへ分離します。
