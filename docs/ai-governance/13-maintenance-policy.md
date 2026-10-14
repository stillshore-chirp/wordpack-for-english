# ガバナンス文書の保守方針

この文書は、WordPack固有の規則、Skill、adapter、validator、fixture、workflowの配置とstatic contractを扱います。共通作業方針は利用環境のローカル規則とユーザー依頼に従います。

## 配置と責務

- repositoryの製品品質・安全・path条件はrootまたは最寄りの`AGENTS.md`に置きます。
- UI/UX、security、production調査などの領域別参照は`.agents/skills/<name>/SKILL.md`に置きます。
- Claude Code / Cursorの`.claude/`・`.cursor/`はrepository内の正本へ接続する薄いadapterです。
- 設計heuristicは[`docs/agent-principles.md`](../agent-principles.md)、UI/UXとIssue本文の品質基準は`docs/ai-governance/`に置きます。
- 形式、存在、参照、source-size、任意task-state形式など、決定的に検査できるrepository契約は`scripts/validate_governance.py`に置きます。static検査を製品runtimeのenforcementとして扱いません。

## 変更時の確認範囲

- 既存の正本、adapter、Skill、validator、CI参照を確認し、同じ判断の複製を増やさず、必要な参照修正を同じ変更に含めます。
- 正本の責務を狭く保ち、新しいcanonical sourceを増やす場合は重複する既存本文の削除または縮約を併せます。
- validatorやfixtureは、検査可能なrepository契約に結び付け、公開可能な合成データを使います。static結果からruntime、Hook、live運用の成功を推定しません。
- CI/workflowの挙動を説明する場合は、現行workflowとpath classifierを一次資料とし、テスト選択の参照先は[`docs/testing/index.md`](../testing/index.md)に保ちます。
- authentication、authorization、data integrity、公開API、production safetyは、利用可能なruntime/config/testに結び付けます。repositoryで検査できない条件は、runtime確認済みと記述しません。
- 過去のreportやevidenceは当時の履歴として保ち、現行ルールを示す参照先と混同しません。

## Static確認

`python3 scripts/validate_governance.py`は、repositoryの構成、frontmatter、参照、source-size、任意task-state形式のstatic gateです。結果はruntime適用やproduction状態の確認を含みません。

変更後は、対象readerからの到達性、canonical link、adapterの薄さ、公開安全性、validatorの対象範囲を確認します。source-size limitはrepository文書の形式上の上限であり、作業時間、agent利用量、製品の実token使用量を示しません。

## 維持する条件

WordPack固有の安全・品質正本への参照が切れている、adapterだけに重要な判断がある、正本間で製品条件が矛盾する、必要なstatic検査が失敗する、公開範囲が未確認の場合は、該当文書を完了扱いにしません。
