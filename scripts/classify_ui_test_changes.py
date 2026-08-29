#!/usr/bin/env python3
"""Classify changed paths for the PR Playwright gates."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Sequence


FRONTEND_SOURCE_PREFIX = "apps/frontend/src/"
BACKEND_RUNTIME_PREFIX = "apps/backend/backend/"
E2E_PREFIX = "tests/e2e/"

SMOKE_POLICY_FILES = {
    ".github/workflows/ci.yml",
}
VISUAL_POLICY_FILES = {
    ".github/workflows/playwright-visual.yml",
}
SHARED_RUNTIME_FILES = {
    ".env.ci",
    ".nvmrc",
    "apps/frontend/index.html",
    "apps/frontend/package-lock.json",
    "apps/frontend/package.json",
    "apps/frontend/tsconfig.build.json",
    "apps/frontend/tsconfig.json",
    "apps/frontend/tsconfig.node.json",
    "apps/frontend/vite.config.ts",
    "package-lock.json",
    "package.json",
    "requirements.txt",
    "scripts/prepare-frontend-env.mjs",
}
SMOKE_E2E_FILES = {
    "tests/e2e/auth.spec.ts",
    "tests/e2e/guest.spec.ts",
    "tests/e2e/helpers.ts",
    "tests/e2e/playwright.config.ts",
    "tests/e2e/wordpack-server-query.spec.ts",
    "tests/e2e/wordpack.spec.ts",
}
VISUAL_E2E_FILES = {
    "tests/e2e/helpers.ts",
    "tests/e2e/playwright.config.ts",
    "tests/e2e/visual.spec.ts",
}
NON_PR_GATE_E2E_FILES = {
    "tests/e2e/errors.spec.ts",
    "tests/e2e/quiz.spec.ts",
    "tests/e2e/shelves.spec.ts",
}
VISUAL_SOURCE_SUFFIXES = {
    ".avif",
    ".css",
    ".gif",
    ".jpeg",
    ".jpg",
    ".less",
    ".otf",
    ".png",
    ".sass",
    ".scss",
    ".svg",
    ".ttf",
    ".tsx",
    ".webp",
    ".woff",
    ".woff2",
}
KNOWN_NON_UI_PREFIXES = (
    ".agents/",
    ".claude/",
    ".cursor/",
    ".github/ISSUE_TEMPLATE/",
    ".github/workflows/",
    "docs/",
    "plans/",
    "scripts/validate_",
    "scripts/verify-",
    "scripts/verify_",
    "tests/fixtures/",
    "終了済みor参考ドキュメント/",
)
KNOWN_NON_UI_FILES = {
    ".env.example",
    ".github/dependabot.yml",
    ".github/pull_request_template.md",
    "AGENTS.md",
    "CLAUDE.md",
    "OPERATIONS.md",
    "README.md",
    "SECURITY.md",
    "UserManual.md",
    "apps/backend/AGENTS.md",
    "apps/frontend/.env.example",
    "apps/frontend/AGENTS.md",
    "env.deploy.example",
    "env.example",
    "requirements-agent-harness.txt",
}


@dataclass(frozen=True)
class UiTestScope:
    playwright_smoke: bool
    playwright_visual: bool


def _normalize_path(raw_path: str) -> str:
    return raw_path.removeprefix("./")


def _is_frontend_test(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return "__tests__" in pure_path.parts or any(
        marker in pure_path.name for marker in (".test.", ".spec.")
    )


def _is_visual_e2e_path(path: str) -> bool:
    return path in VISUAL_E2E_FILES or path.startswith(
        "tests/e2e/visual.spec.ts-snapshots/"
    )


def _classify_path(path: str) -> UiTestScope | None:
    if path in SHARED_RUNTIME_FILES:
        return UiTestScope(playwright_smoke=True, playwright_visual=True)

    if path == "scripts/classify_ui_test_changes.py":
        return UiTestScope(playwright_smoke=True, playwright_visual=True)

    if path in SMOKE_POLICY_FILES:
        return UiTestScope(playwright_smoke=True, playwright_visual=False)

    if path in VISUAL_POLICY_FILES:
        return UiTestScope(playwright_smoke=False, playwright_visual=True)

    if path.startswith(E2E_PREFIX):
        smoke = path in SMOKE_E2E_FILES
        visual = _is_visual_e2e_path(path)
        if smoke or visual:
            return UiTestScope(
                playwright_smoke=smoke,
                playwright_visual=visual,
            )
        if path in NON_PR_GATE_E2E_FILES:
            return UiTestScope(playwright_smoke=False, playwright_visual=False)
        return None

    if path.startswith(BACKEND_RUNTIME_PREFIX):
        return UiTestScope(playwright_smoke=True, playwright_visual=False)

    if path.startswith(FRONTEND_SOURCE_PREFIX) and not _is_frontend_test(path):
        return UiTestScope(
            playwright_smoke=True,
            playwright_visual=PurePosixPath(path).suffix.lower()
            in VISUAL_SOURCE_SUFFIXES,
        )

    if _is_frontend_test(path):
        return UiTestScope(playwright_smoke=False, playwright_visual=False)

    if path.startswith("tests/"):
        return UiTestScope(playwright_smoke=False, playwright_visual=False)

    if path in KNOWN_NON_UI_FILES or path.startswith(KNOWN_NON_UI_PREFIXES):
        return UiTestScope(playwright_smoke=False, playwright_visual=False)

    return None


def classify_paths(paths: Iterable[str]) -> UiTestScope:
    smoke = False
    visual = False
    for raw_path in paths:
        scope = _classify_path(_normalize_path(raw_path))
        if scope is None:
            # 未分類pathは見逃しを避けるため両方のgateを起動する。
            scope = UiTestScope(playwright_smoke=True, playwright_visual=True)
        smoke = smoke or scope.playwright_smoke
        visual = visual or scope.playwright_visual
    return UiTestScope(playwright_smoke=smoke, playwright_visual=visual)


def changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        [
            "git",
            "diff",
            "--name-only",
            "--no-renames",
            "-z",
            f"{base}...{head}",
            "--",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    ]


def _write_github_outputs(output_path: Path, scope: UiTestScope) -> None:
    with output_path.open("a", encoding="utf-8") as output:
        output.write(f"playwright_smoke={str(scope.playwright_smoke).lower()}\n")
        output.write(f"playwright_visual={str(scope.playwright_visual).lower()}\n")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="Base commit SHA or ref")
    parser.add_argument("--head", required=True, help="Head commit SHA or ref")
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Append boolean outputs for a GitHub Actions step",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        paths = changed_paths(args.base, args.head)
    except subprocess.CalledProcessError as error:
        scope = UiTestScope(playwright_smoke=True, playwright_visual=True)
        if args.github_output:
            _write_github_outputs(args.github_output, scope)
        print(
            "::warning title=UI test path classification failed::"
            f"git diff exited with status {error.returncode}; running both UI test gates"
        )
        return 0
    normalized_paths = [_normalize_path(path) for path in paths]
    scope = classify_paths(normalized_paths)
    unknown_paths = [path for path in normalized_paths if _classify_path(path) is None]
    if args.github_output:
        _write_github_outputs(args.github_output, scope)
    for path in unknown_paths[:20]:
        print(f"::warning title=Unclassified UI test path::{path}")
    print(
        json.dumps(
            {
                "changed_path_count": len(paths),
                "unknown_path_count": len(unknown_paths),
                "playwright_smoke": scope.playwright_smoke,
                "playwright_visual": scope.playwright_visual,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
