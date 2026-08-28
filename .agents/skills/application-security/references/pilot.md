# 導入preflight pilot

## 対象

- date: 2026-08-28
- repository: `stillshore-chirp/wordpack-for-english`
- intended scope: Issue #600のagent harness差分
- requested mode: scoped Diff scan
- requested surface: Codex Security cloud
- permission: repository sourceのread、公開安全な要約のみ
- prohibited: production、credential、connected app、外部system更新、exploit実行

## 観測結果

- [公式のCodex Security cloud setup](https://learn.chatgpt.com/docs/security/setup)と、Codex cloudへ接続したGitHub repositoryにenvironmentを作成してからscanを作成する順序を確認した。
- 現環境ではCodex Security cloudのonboarding surfaceへread-onlyで到達できた。
- research previewの個別onboardingと利用同意は完了していない。
- 対象repository用のCodex cloud environmentは作成されていない。
- scan設定は作成されておらず、scanは開始していない。
- account、契約、認証の詳細は公開記録へ保存せず、利用可否の確認済み事実としても扱っていない。

## 判定

- status: `unavailable`
- scan started: no
- product source coverage: 0 files
- findings: not evaluated
- secret / production access: none

通常の差分確認を行ってもCodex Security scanの結果とは扱いません。利用不能をcleanまたは安全と報告せず、許可されたonboardingと利用同意、repositoryのCodex cloud接続、environment作成、scoped scan作成、status・coverage確認を再開条件とします。

## 公開安全な要約

許可済みscopeでread-only preflightを実施しましたが、research preview onboardingと利用同意、対象repositoryのenvironmentが未完了で、scanは開始していません。製品コードの脆弱性有無は未評価です。credential、個人情報、本番情報、攻撃再現情報は取得・公開していません。
