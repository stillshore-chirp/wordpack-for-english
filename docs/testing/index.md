# テスト入口

実行コマンドと変更pathから、focused / full gateを選ぶ入口です。配送順序と証跡の失効は [GitHub配送Skill](../../.agents/skills/github-delivery/SKILL.md) を正本にします。

## CIの選択契約

CIは `main` / `develop` へのpushと、両ブランチを対象とするpull requestで実行します。`verification_scope` が `scripts/classify_verification_inputs.py` の次の11 booleanを出力します。

`backend`, `frontend`, `backend_container`, `deploy_preflight`, `governance`, `workflow_contract`, `dependency_review`, `playwright_smoke`, `playwright_visual`, `playwright_targeted`, `classification_ok`

booleanと同時に `playwright_targeted_specs` をJSON配列で出力します。配列はclassifier内の登録済みfull E2E spec allowlist（`tests/e2e/errors.spec.ts`、`tests/e2e/quiz.spec.ts`、`tests/e2e/shelves.spec.ts`）から、直接変更されたspecだけを重複なく選びます。対象がない場合は空配列です。任意pathは配列へ入りません。

PRは `base...head` の変更pathだけを分類し、`main` pushは `--full` を使います。`develop` pushは直前commitと現在のcommitを分類します。未分類pathまたはdiff取得失敗は `classification_ok=false` としてfail-fastし、skipを成功扱いにしません。

| 変更 | 選択されるgate |
|---|---|
| backend runtime / tests / backend設定 / backend依存 | production Python 3.14 pytest + coverage。`main` pushではPython 3.13 compatibility（`--no-cov`）も実行 |
| frontend runtime / 設定 / 依存 | typecheck + Vitest。PRと`develop`はno coverage、`main` pushはcoverage |
| container定義 | `backend_container`。該当変更と`main` pushで実行 |
| deploy script / Cloud Run設定 | static `deploy_preflight`。該当変更と`main` pushで実行 |
| agent / governance / `docs/testing/index.md` | `python scripts/validate_governance.py` の後に `python -m pytest -q --no-cov tests/test_agent_harness_budget.py tests/test_governance_task_state.py tests/test_validate_governance.py tests/test_public_docs_security.py tests/test_security_scan_text.py` |
| workflow / classifier / workflow contract test | `workflow_contract` とYAML parseのcontract |
| E2E smoke / 登録済みfull spec / visual、frontend共有runtime | classifierが選んだPlaywright job。通常smokeが選択された場合は既存smoke一覧と `playwright_targeted_specs` を同じsmoke jobで重複なく実行し、targeted full specだけの場合も同じjobを再利用します。visualは `playwright_visual` の独立jobで従来どおり実行し、targeted full specの選択へ依存しません。smokeとvisualはclassifier直後に並行開始 |
| すべてのCI実行 | `security_text_scan`。最後にstable `quality_gate` がclassifierの選択と各jobのresultを照合 |

独立したCodeQL、OpenSSF Scorecard、backend performance、全Playwright回帰は、weekly scheduleとmanual dispatchの `scheduled-maintenance.yml` に統合しています。scheduleは4 suiteを実行し、manual dispatchは `suite`（`all` / `codeql` / `scorecard` / `backend-performance` / `playwright`）で選択したsuiteだけを実行します。dependency reviewは既存のdependency関連path filterを維持し、PRのdependency-bearing path（package manifest/lock、requirements、pyproject/poetry、Dockerfile、dependabot等）がある時だけDependency Graph probe/actionを実行します。workflow-only変更ではprobe/actionをskipしてjobを成功させ、changed-path判定の失敗はfail-closedにします。

## ローカルでよく使うコマンド

| 種別 | コマンド | 詳細 |
|---|---|---|
| Backend full gate | `PYTHONPATH=apps/backend pytest` | `pytest.ini` のcoverage付き全体検証。security headersもこのsuiteに含む |
| Backend focused | `PYTHONPATH=apps/backend pytest -q --no-cov <test-or-node>` | coverageを目的としないfocused pytest |
| Backend architecture | `PYTHONPATH=apps/backend pytest -q --no-cov tests/backend/test_architecture_boundaries.py` | 禁止importとruntime直呼び出しを検査 |
| Frontend PR相当 | `cd apps/frontend && npm test -- --no-coverage --silent` | Vitestのみ。typecheckは `npx tsc -p tsconfig.json` |
| Frontend main相当 | `cd apps/frontend && npm test -- --coverage --silent` | coverage付きVitest |
| Workflow / classifier contract | `python -m pytest -q --no-cov tests/test_github_actions_branch_policy.py tests/test_verification_inputs.py tests/test_scheduled_maintenance_workflow.py` | workflow条件、scheduled maintenanceのsuite選択、gate入力閉包、出力interface |
| Workflow YAML parse | `python3 -c 'import yaml; yaml.safe_load(open(".github/workflows/scheduled-maintenance.yml", encoding="utf-8"))'` | このlaneのowned workflowだけ構文を確認 |
| Gate-input classification（PR） | `python3 scripts/classify_verification_inputs.py --base "$BASE_SHA" --head "$HEAD_SHA"` | `base...head` の11 gate boolean、`playwright_targeted_specs` JSON配列、`classification_ok` を確認 |
| Gate-input classification（main） | `python3 scripts/classify_verification_inputs.py --full` | full profileの選択を確認 |
| Governance static + contract check | `python3 scripts/validate_governance.py && python -m pytest -q --no-cov tests/test_agent_harness_budget.py tests/test_governance_task_state.py tests/test_validate_governance.py tests/test_public_docs_security.py tests/test_security_scan_text.py` | 正本、Skill、adapter、frontmatter、link、budget、公開テキストとtask-stateを確認 |

Firestore Emulator付きbackend CIはJava 21を使います。Playwright、Docker、全suiteの実行はCIの選択jobに委ね、このlaneのローカル検証では起動しません。

## 実行判断と成果物

変更path、関連設定・依存・生成物、実行条件を同じ入力閉包として扱います。workflow/classifier変更はcontract testとYAML parseを再取得し、governance変更はstatic validationを再取得します。文書だけの変更でもclassifierがgovernanceを選ぶ場合はそのjobを実行します。

Playwrightの `playwright-report/` と `test-results/` は失敗時だけartifact化し、保持期間は14日です。pytest / Vitest coverageは各設定に従います。成果物は通常Gitへcommitせず、CIではGitHub Actions artifactsから確認します。
