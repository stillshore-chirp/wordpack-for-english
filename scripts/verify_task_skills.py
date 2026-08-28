#!/usr/bin/env python3
"""Validate canonical task Skills, routers, and thin Claude Code adapters."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = ROOT / ".agents" / "skills"
CLAUDE_ROOT = ROOT / ".claude" / "skills"
AGENTS = ROOT / "AGENTS.md"
COMMON_CORE_DOCS = (ROOT / "docs" / "agent-harness.md",)
MAX_ROOT_LINES = 180
MAX_ROOT_BYTES = 16_384
MAX_NESTED_LINES = 100
MAX_NESTED_BYTES = 8_192
MAX_COMBINED_BYTES = 24_576
MAX_SKILL_LINES = 180
MAX_SKILL_BYTES = 16_384
MAX_ADAPTER_LINES = 30
MAX_ADAPTER_BYTES = 4_096
MAX_REFERENCE_BYTES = 32_768
LINK_PATTERN = re.compile(r"\]\(([^)]+)\)")
FENCED_CODE_PATTERN = re.compile(r"(?ms)^\s*(```|~~~).*?^\s*\1\s*$")
HTML_COMMENT_PATTERN = re.compile(r"<!--.*?-->", re.DOTALL)
LOCAL_PATH_PATTERNS = ("/Users/", "/home/", "C:\\Users\\")
TOOL_COMMAND_PATTERNS = (
    "start_codex_security_",
    "get_codex_security_",
    "complete_codex_security_",
    "plugin-eval ",
)
TEXT_SUFFIXES = {".md", ".json", ".py", ".sh", ".txt", ".csv", ".yml", ".yaml"}
EXCLUDED_ROUTER_PARTS = {".git", ".external", ".venv", "node_modules"}


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def relative(path: Path, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"required file missing: {relative(path)}")


def discover_router_files(root: Path = ROOT) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("AGENTS.md")
        if not EXCLUDED_ROUTER_PARTS.intersection(path.relative_to(root).parts)
    )


def budget_errors(raw: bytes, max_lines: int, max_bytes: int) -> list[str]:
    lines = len(raw.decode("utf-8").splitlines())
    errors = []
    if lines > max_lines:
        errors.append(f"exceeds {max_lines} lines: {lines}")
    if len(raw) > max_bytes:
        errors.append(f"exceeds {max_bytes} bytes: {len(raw)}")
    return errors


def check_budget(path: Path, max_lines: int, max_bytes: int) -> None:
    for error in budget_errors(path.read_bytes(), max_lines, max_bytes):
        fail(f"{relative(path)} {error}")


def check_router_budget(path: Path, root_raw: bytes) -> None:
    raw = path.read_bytes()
    if path == AGENTS:
        errors = budget_errors(raw, MAX_ROOT_LINES, MAX_ROOT_BYTES)
    else:
        errors = budget_errors(raw, MAX_NESTED_LINES, MAX_NESTED_BYTES)
        combined_bytes = len(root_raw) + len(raw)
        if combined_bytes > MAX_COMBINED_BYTES:
            errors.append(
                f"root plus nested exceeds {MAX_COMBINED_BYTES} bytes: {combined_bytes}"
            )
    for error in errors:
        fail(f"{relative(path)} {error}")


def local_markdown_targets(
    router_path: Path,
    content: str,
    root: Path = ROOT,
) -> set[Path]:
    rendered = HTML_COMMENT_PATTERN.sub("", content)
    rendered = FENCED_CODE_PATTERN.sub("", rendered)
    targets: set[Path] = set()
    for match in LINK_PATTERN.finditer(rendered):
        target = unquote(match.group(1).strip())
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        target = target.split("#", 1)[0].strip()
        if not target or target.startswith(("https://", "http://", "mailto:")):
            continue
        resolved = (router_path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        targets.add(resolved)
    return targets


def check_portability(path: Path, content: str) -> None:
    if any(pattern in content for pattern in LOCAL_PATH_PATTERNS):
        fail(f"{relative(path)} contains a machine-local absolute path")


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


def check_skill_tree(skill_path: Path) -> None:
    for path in skill_path.parent.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        content = read_text(path)
        check_portability(path, content)
        if path != skill_path and len(content.encode("utf-8")) > MAX_REFERENCE_BYTES:
            fail(f"{relative(path)} exceeds {MAX_REFERENCE_BYTES} bytes")


def run_self_test() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        skill = root / ".agents" / "skills" / "sample" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        skill.write_text("---\nname: sample\ndescription: sample\n---\n", encoding="utf-8")
        router = root / "AGENTS.md"

        exact = "[sample](.agents/skills/sample/SKILL.md)\n"
        if skill.resolve() not in local_markdown_targets(router, exact, root):
            fail("self-test failed: exact router link was not resolved")

        broken = "[sample](.agents/skills/sample/SKILL.md.bak)\n"
        if skill.resolve() in local_markdown_targets(router, broken, root):
            fail("self-test failed: prefix-only router link was accepted")

        hidden = (
            "<!-- [sample](.agents/skills/sample/SKILL.md) -->\n"
            "```md\n[sample](.agents/skills/sample/SKILL.md)\n```\n"
        )
        if skill.resolve() in local_markdown_targets(router, hidden, root):
            fail("self-test failed: non-rendered router link was accepted")

        oversized = ("line\n" * (MAX_NESTED_LINES + 1)).encode()
        if not budget_errors(oversized, MAX_NESTED_LINES, MAX_NESTED_BYTES):
            fail("self-test failed: oversized nested router was accepted")
        too_wide = ("x" * (MAX_NESTED_BYTES + 1)).encode()
        if not any("bytes" in error for error in budget_errors(too_wide, 1, MAX_NESTED_BYTES)):
            fail("self-test failed: oversized nested router bytes were accepted")

    print("Task Skill verifier self-test: PASS")


def verify_repository() -> int:
    canonical = sorted(CANONICAL_ROOT.glob("*/SKILL.md"))
    adapters = sorted(CLAUDE_ROOT.glob("*/SKILL.md"))
    router_files = discover_router_files()
    if not canonical:
        fail("no canonical task Skills found")
    if AGENTS not in router_files:
        fail("root AGENTS.md router missing")

    root_raw = AGENTS.read_bytes()
    router_targets: set[Path] = set()
    for path in router_files:
        check_router_budget(path, root_raw)
        router_targets.update(local_markdown_targets(path, read_text(path)))

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
        if skill_path.resolve() not in router_targets:
            fail(f"an AGENTS.md must link exactly to {canonical_path}")
        check_reference_links(skill_path, content)
        check_skill_tree(skill_path)

        adapter_path = CLAUDE_ROOT / skill_path.parent.name / "SKILL.md"
        adapter = read_text(adapter_path)
        check_budget(adapter_path, MAX_ADAPTER_LINES, MAX_ADAPTER_BYTES)
        check_portability(adapter_path, adapter)
        if "唯一の手順正本" not in adapter:
            fail(f"{relative(adapter_path)} must identify the canonical Skill")
        expected_link = f"../../../{canonical_path}"
        if expected_link not in adapter:
            fail(f"{relative(adapter_path)} must link to {expected_link}")

    for path in [*router_files, *COMMON_CORE_DOCS]:
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    if parse_args().self_test:
        run_self_test()
        return 0
    return verify_repository()


if __name__ == "__main__":
    raise SystemExit(main())
