from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.classify_ui_test_changes import (
    UiTestScope,
    changed_paths,
    classify_paths,
    main,
)


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (
            ["docs/agent-harness.md", ".agents/skills/ui-ux-review/SKILL.md"],
            UiTestScope(playwright_smoke=False, playwright_visual=False),
        ),
        (
            [
                "apps/frontend/src/components/Modal.test.tsx",
                "apps/frontend/src/features/quiz/progress.test.ts",
                "apps/frontend/src/__tests__/App.test.tsx",
            ],
            UiTestScope(playwright_smoke=False, playwright_visual=False),
        ),
        (
            ["apps/frontend/src/lib/date.ts"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["apps/frontend/src/content.json"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["apps/frontend/src/pages/QuizPage/index.tsx"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["apps/frontend/src/shared/styles/tokens.css"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["apps/frontend/src/env.d.ts"],
            UiTestScope(playwright_smoke=False, playwright_visual=False),
        ),
        (
            ["apps/backend/backend/routers/wordpacks.py"],
            UiTestScope(playwright_smoke=True, playwright_visual=False),
        ),
        (
            ["tests/e2e/auth.spec.ts"],
            UiTestScope(playwright_smoke=True, playwright_visual=False),
        ),
        (
            ["tests/e2e/quiz.spec.ts"],
            UiTestScope(playwright_smoke=False, playwright_visual=False),
        ),
        (
            ["tests/e2e/new-shared-helper.ts"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["tests/e2e/visual.spec.ts-snapshots/wordpack-list-linux.png"],
            UiTestScope(playwright_smoke=False, playwright_visual=True),
        ),
        (
            ["apps/frontend/package-lock.json"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            [".github/workflows/ci.yml"],
            UiTestScope(playwright_smoke=True, playwright_visual=False),
        ),
        (
            [".github/workflows/playwright-visual.yml"],
            UiTestScope(playwright_smoke=False, playwright_visual=True),
        ),
        (
            ["scripts/classify_ui_test_changes.py"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
        (
            ["new-runtime-surface/config.toml"],
            UiTestScope(playwright_smoke=True, playwright_visual=True),
        ),
    ],
)
def test_classify_paths_matches_ui_test_responsibilities(
    paths: list[str], expected: UiTestScope
) -> None:
    assert classify_paths(paths) == expected


def test_classify_paths_combines_independent_changes() -> None:
    assert classify_paths(
        [
            "apps/backend/backend/main.py",
            "apps/frontend/src/pages/QuizPage/QuizPage.css",
        ]
    ) == UiTestScope(playwright_smoke=True, playwright_visual=True)


def test_issue_619_governance_only_paths_skip_ui_tests() -> None:
    assert classify_paths(
        [
            ".agents/skills/github-delivery/SKILL.md",
            ".github/workflows/agent-harness.yml",
            "AGENTS.md",
            "docs/agent-harness.md",
            "docs/ai-governance/13-maintenance-policy.md",
            "scripts/verify-agent-harness.sh",
        ]
    ) == UiTestScope(playwright_smoke=False, playwright_visual=False)


def test_changed_paths_keeps_both_sides_of_renames(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded_command: list[str] = []

    def fake_run(command: list[str], **_: object) -> object:
        recorded_command.extend(command)
        return type("Completed", (), {"stdout": b"old/path.tsx\0new/path.tsx\0"})()

    monkeypatch.setattr("scripts.classify_ui_test_changes.subprocess.run", fake_run)

    assert changed_paths("base", "head") == ["old/path.tsx", "new/path.tsx"]
    assert "--no-renames" in recorded_command
    assert "base...head" in recorded_command


def test_main_runs_both_gates_when_diff_classification_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_path = tmp_path / "github-output"

    def fail_diff(_: str, __: str) -> list[str]:
        raise subprocess.CalledProcessError(returncode=128, cmd=["git", "diff"])

    monkeypatch.setattr("scripts.classify_ui_test_changes.changed_paths", fail_diff)

    assert (
        main(
            [
                "--base",
                "missing-base",
                "--head",
                "head",
                "--github-output",
                str(output_path),
            ]
        )
        == 0
    )
    assert output_path.read_text(encoding="utf-8").splitlines() == [
        "playwright_smoke=true",
        "playwright_visual=true",
    ]
