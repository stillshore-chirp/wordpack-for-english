# テスト入口

実行コマンドと変更pathから、focused / full gateを選ぶ入口です。配送順序と証跡の失効は [GitHub配送Skill](../../.agents/skills/github-delivery/SKILL.md) を正本にします。

## CIの選択契約

CIは `main` / `develop` へのpushと、両ブランチを対象とするpull requestで実行します。`verification_scope` が `scripts/classify_verification_inputs.py` の次の9 booleanを出力します。

`backend`, `frontend`, `backend_container`, `deploy_preflight`, `governance`, `workflow_contract`, `playwright_smoke`, `playwright_visual`, `classification_ok`

PRは `base...head` の変更pathだけを分類し、`main` pushは `--full` を使います。`develop` pushは直前commitと現在のcommitを分類します。未分類pathまたはdiff取得失敗は `classification_ok=false` としてfail-fastし、skipを成功扱いにしません。

| 変更 | 選択されるgate |
|---|---|
| backend runtime / tests / backend設定 / backend依存 | production Python 3.14 pytest + coverage。`main` pushではPython 3.13 compatibility（`--no-cov`）も実行 |
| frontend runtime / 設定 / 依存 | typecheck + Vitest。PRと`develop`はno coverage、`main` pushはcoverage |
| container定義 | `backend_container`。該当変更と`main` pushで実行 |
| deploy script / Cloud Run設定 | static `deploy_preflight`。該当変更と`main` pushで実行 |
| agent / governance / `docs/testing/index.md` | `python scripts/validate_governance.py` |
| workflow / classifier / workflow contract test | `workflow_contract` とYAML parseのcontract |
| E2E smoke / visual、frontend共有runtime | classifierが選んだPlaywright job。smokeとvisualはclassifier直後に並行開始 |
| すべてのCI実行 | `security_text_scan`。最後にstable `quality_gate` がclassifierの選択と各jobのresultを照合 |

独立したCodeQLは `main` push、weekly schedule、manual dispatchに限定します。全Playwright回帰はweekly scheduleとmanual dispatchの `playwright-nightly.yml` で実行します。dependency reviewは既存のdependency関連path filterを維持し、Dependency Graph取得失敗をfail-closedにします。

## ローカルでよく使うコマンド

| 種別 | コマンド | 詳細 |
|---|---|---|
| Backend full gate | `PYTHONPATH=apps/backend pytest` | `pytest.ini` のcoverage付き全体検証。security headersもこのsuiteに含む |
| Backend focused | `PYTHONPATH=apps/backend pytest -q --no-cov <test-or-node>` | coverageを目的としないfocused pytest |
| Backend architecture | `PYTHONPATH=apps/backend pytest -q --no-cov tests/backend/test_architecture_boundaries.py` | 禁止importとruntime直呼び出しを検査 |
| Frontend PR相当 | `cd apps/frontend && npm test -- --no-coverage --silent` | Vitestのみ。typecheckは `npx tsc -p tsconfig.json` |
| Frontend main相当 | `cd apps/frontend && npm test -- --coverage --silent` | coverage付きVitest |
| Workflow / classifier contract | `python -m pytest -q --no-cov tests/test_github_actions_branch_policy.py tests/test_verification_inputs.py` | workflow条件、gate入力閉包、出力interface |
| Workflow YAML parse | `python3 -c 'import pathlib,yaml; [yaml.safe_load(p.read_text(encoding="utf-8")) for p in pathlib.Path(".github/workflows").glob("*.y*ml")]'` | 全workflowの構文を確認 |
| Gate-input classification（PR） | `python3 scripts/classify_verification_inputs.py --base "$BASE_SHA" --head "$HEAD_SHA"` | `base...head` の9 gate booleanと `classification_ok` を確認 |
| Gate-input classification（main） | `python3 scripts/classify_verification_inputs.py --full` | full profileの選択を確認 |
| Governance static check | `python3 scripts/validate_governance.py` | 正本、Skill、adapter、frontmatter、link、budgetを確認 |

Firestore Emulator付きbackend CIはJava 21を使います。Playwright、Docker、全suiteの実行はCIの選択jobに委ね、このlaneのローカル検証では起動しません。

## 実行判断と成果物

変更path、関連設定・依存・生成物、実行条件を同じ入力閉包として扱います。workflow/classifier変更はcontract testとYAML parseを再取得し、governance変更はstatic validationを再取得します。文書だけの変更でもclassifierがgovernanceを選ぶ場合はそのjobを実行します。

Playwrightの `playwright-report/` と `test-results/` は失敗時だけartifact化し、保持期間は14日です。pytest / Vitest coverageは各設定に従います。成果物は通常Gitへcommitせず、CIではGitHub Actions artifactsから確認します。
