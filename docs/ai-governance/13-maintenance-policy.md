# ガバナンス保守方針

この文書は、rule、Skill、adapter、validator、fixture、self-test、workflowを増減・変更する判断基準です。3製品の読者、委任、evidence、task-stateは [`docs/agent-harness.md`](../agent-harness.md) を正本とします。

## 配置と責務

- 全体のhard gate・権限・最小実行は`AGENTS.md`、path契約は最寄りの`AGENTS.md`、task手順は`.agents/skills/<name>/SKILL.md`に置きます。
- Claude Code / Cursorの`.claude/`・`.cursor/`は薄いrouterです。判断基準や長文手順を置きません。
- 形式・存在・参照・budgetなど決定的に判定できるものだけを`scripts/validate_governance.py`へ置き、製品runtimeのenforcementを代用しません。

## 追加・変更・削除の基準

各変更は、対象scope、発動条件、正本owner、enforcement（static / test / runtime / advisory）、coverage、関連incidentまたはrisk、instruction・実行cost、sunsetまたはreplacementを先に記録します。

- 追加前に既存正本・adapter・Skill・validator・fixture・self-test・workflowを検索し、統合またはreplacementを先に検討します。正本を二つに増やすための要約・複製を追加しません。
- ruleは全体、path、taskのどの層かを固定し、adapterには接続だけを残します。新しいcanonical sourceを増やす場合は既存正本を削除・縮約する移行を同じ変更に含めます。
- validator・self-test・fixtureは、検査可能な契約と回帰条件へ直接結び付け、syntheticで公開安全な入力を使います。static結果を実runtime、Hook、live benchmarkの成功と表現しません。
- workflow/job変更はfailure mode、trigger locus（PR / main / scheduled / manual）、estimated runner・wall-clock cost、artifact、failure owner、既存gate統合では不十分な理由、sunsetまたはadvisoryへのdemotion条件を明示します。
- security、authorization、data integrity、公開API、production safetyの境界は、利用可能ならruntime/config/testの機械的enforcementへ結び付けます。repositoryでenforceできない部分はadvisory / unverifiedとして残し、app-only挙動を疑似実装しません。
- 削除はconsumer、link、coverage、replacement、sunset理由を確認し、到達不能なhard gateや未追跡のincidentを残しません。

soft heuristicは、自然言語のexact-match検査や大規模scenario fixtureで固定しません。判断理由と観測可能な結果を保ち、必要な機械検査だけを追加します。

## 保守ゲート

変更前に対象path、正本、読者、必要な検証、owner、公開範囲を確認します。変更後は3製品の到達性、frontmatter、重要link、budget、重複、公開安全性、関連fixture/self-testを確認します。

`python3 scripts/validate_governance.py`はstatic gateです。失敗、未確認、coverage不足、runtime未観測は、理由と再取得範囲を分けて記録します。source-size budgetはestimateであり、Hook注入量やobserved token telemetryではありません。

## 停止条件

共通hard gateへ到達できない、adapterだけに重要判断がある、正本間で条件が食い違う、replacementなしの増加、owner・enforcement・coverage・cost・sunsetが未確定、budget超過、壊れたlink、公開範囲未確認がある場合は完了扱いにしません。
