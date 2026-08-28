#!/usr/bin/env python3
"""Validate canonical task Skills and thin Claude Code adapters."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = ROOT / ".agents" / "skills"
CLAUDE_ROOT = ROOT / ".claude" / "skills"
AGENTS = ROOT / "AGENTS.md"
COMMON_CORE = (
    AGENTS,
    ROOT / "docs" / "agent-harness.md",
    ROOT / "apps" / "frontend" / "AGENTS.md",
    ROOT / "apps" / "backend" / "AGENTS.md",
    ROOT / "docs" / "operations" / "AGENTS.md",
)
MAX_SKILL_LINES = 180
MAX_SKILL_BYTES = 16_384
MAX_ADAPTER_LINES = 30
MAX_ADAPTER_BYTES = 4_096
LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
LOCAL_PATH_PATTERNS = ("/Users/", "/home/", "C:\\Users\\")
TOOL_COMMAND_PATTERNS = (
    "start_codex_security_",
    "get_codex_security_",
    "complete_codex_security_",
)
EXCLUDED_ROUTER_PARTS = {".git", ".external", ".venv", "node_modules"}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"required file missing: {relative(path)}")


def discover_router_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("AGENTS.md")
        if not EXCLUDED_ROUTER_PARTS.intersection(path.relative_to(ROOT).parts)
    )


def check_budget(path: Path, max_lines: int, max_bytes: int) -> None:
    raw = path.read_bytes()
    lines = len(raw.decode("utf-8").splitlines())
    if lines > max_lines:
        fail(f"{relative(path)} exceeds {max_lines} lines: {lines}")
    if len(raw) > max_bytes:
        fail(f"{relative(path)} exceeds {max_bytes} bytes: {len(raw)}")


def check_reference_links(skill_path: Path, content: str) -> None:
    for match in LINK_PATTERN.finditer(content):
        target = unquote(match.group(1).split("#", 1)[0].strip())
        if not target.startswith("references/"):
            continue
        resolved = (skill_path.parent / target).resolve()
        try:
            resolved.relative_to(skill_path.parent.resolve())
        except ValueError:
            fail(f"{relative(skill_path)} reference escapes its Skill directory: {target}")
        if not resolved.is_file():
            fail(f"{relative(skill_path)} has a broken reference: {target}")


def main() -> int:
    canonical = sorted(CANONICAL_ROOT.glob("*/SKILL.md"))
    adapters = sorted(CLAUDE_ROOT.glob("*/SKILL.md"))
    router_files = discover_router_files()
    if not canonical:
        fail("no canonical task Skills found")
    if not router_files:
        fail("no AGENTS.md router files found")

    router_texts = {path: read_text(path) for path in router_files}
    canonical_names = {path.parent.name for path in canonical}
    adapter_names = {path.parent.name for path in adapters}

    missing_adapters = sorted(canonical_names - adapter_names)
    orphan_adapters = sorted(adapter_names - canonical_names)
    if missing_adapters:
        fail(f"Claude adapters missing for: {', '.join(missing_adapters)}")
    if orphan_adapters:
        fail(f"Claude adapters without canonical Skill: {', '.join(orphan_adapters)}")

    for skill_path in canonical:
        content = read_text(skill_path)
        check_budget(skill_path, MAX_SKILL_LINES, MAX_SKILL_BYTES)
        canonical_path = relative(skill_path)
        if not any(canonical_path in text for text in router_texts.values()):
            fail(f"an AGENTS.md must route to {canonical_path}")
        if any(pattern in content for pattern in LOCAL_PATH_PATTERNS):
            fail(f"{canonical_path} contains a machine-local absolute path")
        check_reference_links(skill_path, content)

        adapter_path = CLAUDE_ROOT / skill_path.parent.name / "SKILL.md"
        adapter = read_text(adapter_path)
        check_budget(adapter_path, MAX_ADAPTER_LINES, MAX_ADAPTER_BYTES)
        if "唯一の手順正本" not in adapter:
            fail(f"{relative(adapter_path)} must identify the canonical Skill")
        expected_link = f"../../../{canonical_path}"
        if expected_link not in adapter:
            fail(f"{relative(adapter_path)} must link to {expected_link}")
        if any(pattern in adapter for pattern in LOCAL_PATH_PATTERNS):
            fail(f"{relative(adapter_path)} contains a machine-local absolute path")

    for path in COMMON_CORE:
        content = read_text(path)
        for pattern in TOOL_COMMAND_PATTERNS:
            if pattern in content:
                fail(f"{relative(path)} contains tool-specific command text: {pattern}")

    validator = ROOT / "scripts" / "validate_agent_frontmatter.py"
    subprocess.run(
        [sys.executable, str(validator), *map(str, canonical), *map(str, adapters)],
        cwd=ROOT,
        check=True,
    )

    print(
        f"Task Skill verification: PASS "
        f"({len(canonical)} canonical, {len(adapters)} adapters, {len(router_files)} routers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
