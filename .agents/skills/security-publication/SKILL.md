---
name: security-publication
description: "公開リポジトリへpushされる文書、Issue、PR、レポート、ログ要約、サンプル、スクリーンショットを作成・更新する時に、秘密情報や追跡可能な運用情報の露出を防ぐ。"
---

# 公開安全性 Skill

## 発動条件

gitへpushされる文書、Issue / PR本文、運用記録、調査レポート、sample、fixture、screenshot、traceの追加・更新で使います。詳細正本は [`docs/security-publication-checklist.md`](../../../docs/security-publication-checklist.md) です。

## 1. 対象の棚卸し

- 公開先と、追加・更新する全ファイル、Issue / PR本文、添付物を列挙する。
- source、generated artifact、log、screenshot、sample dataを区別する。
- 外部入力をそのまま転載していないか確認する。

## 2. 公開禁止または最小化する情報

- secret、API key、token、Cookie、認証header、private key
- 個人情報、ユーザー入力全文、メールアドレス、内部連絡先
- 本番ログ原文、完全なquery、正確なrevision名、秒単位時刻
- 実request / trace / job / session ID
- 不要なproject、service、bucket、databaseなどの本番識別子
- ローカルpath、credential store、認証状態の詳細
- 攻撃に直接使える未修正脆弱性の過剰な再現情報

必要な事実だけを要約し、識別子は一般化またはマスクする。

## 3. 検査

- 差分と新規ファイルを目視する。
- secret scanner、不可視文字、`git diff --check`、リンク確認など利用可能な検査を実行する。
- screenshot、trace、video、test artifactは、画面外やmetadataも確認する。
- sample / fixtureは実データのコピーを避け、匿名の最小データを使う。
- 公開判断が不明な値は、公開しない側に倒す。

## 4. 承認が必要な場合

公開操作が安全審査で停止した場合、許可だけを求めない。値そのものを再表示せず、次を先に示す。

- 公開先と操作
- 対象の完全な一覧
- マスク済みの差分または安全な説明
- 具体的な疑いか、予防的停止か
- 実施済み検査
- 未確認範囲
- 推奨判断と必要な安全措置

## 5. 漏洩を発見した場合

- 追加の公開・pushを止める。
- 値を回答やIssueへ再掲しない。
- secretならrotate / revokeを優先する。
- 履歴、cache、artifact、forkへの残存範囲を評価する。
- 文書修正だけで完了扱いにしない。

## 6. 報告

公開安全性の確認範囲、実行した検査、検出結果、一般化した値、未確認項目、残るリスクをPRへ記載する。
