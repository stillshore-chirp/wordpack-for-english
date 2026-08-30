#!/usr/bin/env python3
"""Validate the static structure of the agent-governance surface."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlsplit

import yaml
from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
LIMITS = {
    "root": (180, 16_384),
    "nested": (100, 8_192),
    "skill": (180, 16_384),
    "adapter": (30, 4_096),
}
COMBINED_ROUTER_BYTES = 24_576
REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "docs/agent-principles.md",
    "docs/agent-harness.md",
    "docs/ai-governance/00-index.md",
    "docs/ai-governance/13-maintenance-policy.md",
    "scripts/validate_governance.py",
)
REQUIRED_RULES = tuple(
    f"{root}/{name}"
    for root, names in (
        (".claude/rules", ("agent-harness.md", "frontend.md", "backend.md", "operations.md")),
        (".cursor/rules", ("agent-harness.mdc", "frontend.mdc", "backend.mdc", "operations.mdc")),
    )
    for name in names
)
SKILL_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*$")


class GovernanceError(ValueError):
    """Raised when the static governance structure is invalid."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _mapping(loader: UniqueKeyLoader, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise GovernanceError(f"duplicate frontmatter key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def fail(message: str) -> None:
    raise GovernanceError(message)


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        fail(f"cannot read {path}: {error}")


def require_file(path: Path, root: Path) -> None:
    if not path.is_file():
        fail(f"required file missing: {rel(path, root)}")


def budget(path: Path, root: Path, kind: str) -> None:
    require_file(path, root)
    raw = path.read_bytes()
    lines, bytes_limit = LIMITS[kind]
    try:
        count = len(raw.decode("utf-8").splitlines())
    except UnicodeDecodeError as error:
        fail(f"{rel(path, root)} is not UTF-8: {error}")
    if count > lines:
        fail(f"{rel(path, root)} exceeds {lines} lines: {count}")
    if len(raw) > bytes_limit:
        fail(f"{rel(path, root)} exceeds {bytes_limit} bytes: {len(raw)}")


def load_frontmatter(path: Path, root: Path) -> dict[str, Any]:
    lines = text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        fail(f"{rel(path, root)} frontmatter must start on the first line")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as error:
        fail(f"{rel(path, root)} frontmatter closing delimiter is missing")
        raise AssertionError from error
    try:
        value = yaml.load("\n".join(lines[1:end]), Loader=UniqueKeyLoader)
    except (yaml.YAMLError, GovernanceError) as error:
        fail(f"{rel(path, root)} invalid frontmatter: {error}")
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        fail(f"{rel(path, root)} frontmatter must be a string-keyed mapping")
    return value


def required_string(data: dict[str, Any], key: str, path: Path, root: Path) -> None:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        fail(f"{rel(path, root)} frontmatter {key} must be a non-empty string")


def validate_frontmatter(path: Path, root: Path) -> None:
    data = load_frontmatter(path, root)
    try:
        parts = path.relative_to(root).parts
    except ValueError as error:
        fail(f"frontmatter path is outside repository: {path}")
        raise AssertionError from error
    if len(parts) >= 3 and parts[:2] in ((".agents", "skills"), (".claude", "skills")):
        required_string(data, "name", path, root)
        required_string(data, "description", path, root)
        if SKILL_NAME.fullmatch(data["name"]) is None:
            fail(f"{rel(path, root)} frontmatter name is not kebab-case")
    elif len(parts) >= 3 and parts[:2] == (".claude", "rules"):
        values = data.get("paths")
        if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item.strip() for item in values):
            fail(f"{rel(path, root)} frontmatter paths must be a non-empty string list")
    elif len(parts) >= 3 and parts[:2] == (".cursor", "rules"):
        required_string(data, "description", path, root)
        globs = data.get("globs")
        if not ((isinstance(globs, str) and globs.strip()) or (isinstance(globs, list) and globs and all(isinstance(item, str) and item.strip() for item in globs))):
            fail(f"{rel(path, root)} frontmatter globs must be a non-empty string or list")
        if data.get("alwaysApply") is not False:
            fail(f"{rel(path, root)} frontmatter alwaysApply must be false")
    else:
        fail(f"cannot infer frontmatter kind for {rel(path, root)}")


def markdown_targets(path: Path, root: Path) -> Iterable[Path]:
    for token in MarkdownIt("commonmark").parse(text(path)):
        if token.type != "inline":
            continue
        for child in token.children or []:
            if child.type == "link_open":
                raw = child.attrGet("href")
            elif child.type == "image":
                raw = child.attrGet("src")
            else:
                continue
            if not raw:
                continue
            parsed = urlsplit(unquote(raw.strip()))
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            candidate = (root / parsed.path.lstrip("/") if parsed.path.startswith("/") else path.parent / parsed.path).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                fail(f"{rel(path, root)} link escapes repository: {parsed.path}")
            yield candidate


def validate_links(paths: Iterable[Path], root: Path) -> None:
    pending = list(paths)
    visited: set[Path] = set()
    while pending:
        path = pending.pop()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        for candidate in markdown_targets(path, root):
            if not candidate.exists():
                fail(f"{rel(path, root)} has a broken local link: {rel(candidate, root)}")
            if candidate.suffix.lower() in {".md", ".mdc", ".markdown"}:
                pending.append(candidate)


def discover_routers(root: Path) -> list[Path]:
    excluded = {".git", ".venv", "node_modules", ".external"}
    return sorted(path for path in root.rglob("AGENTS.md") if not excluded.intersection(path.relative_to(root).parts))


def validate_skills(root: Path, routers: list[Path]) -> tuple[int, int, int]:
    canonical = sorted((root / ".agents/skills").glob("*/SKILL.md"))
    adapters = sorted((root / ".claude/skills").glob("*/SKILL.md"))
    if not canonical:
        fail("no canonical task Skills found")
    if {path.parent.name for path in canonical} != {path.parent.name for path in adapters}:
        fail("canonical Skills and Claude adapters must have the same names")
    targets = {candidate for router in routers for candidate in markdown_targets(router, root)}
    for skill in canonical:
        budget(skill, root, "skill")
        validate_frontmatter(skill, root)
        if skill.resolve() not in targets:
            fail(f"an AGENTS.md must link to {rel(skill, root)}")
        adapter = root / ".claude/skills" / skill.parent.name / "SKILL.md"
        budget(adapter, root, "adapter")
        validate_frontmatter(adapter, root)
        if skill.resolve() not in set(markdown_targets(adapter, root)):
            fail(f"{rel(adapter, root)} must link to {rel(skill, root)}")
    return len(canonical), len(adapters), len(routers)


def validate_repository(root: Path) -> tuple[int, int, int]:
    files = [root / path for path in REQUIRED_FILES]
    rules = [root / path for path in REQUIRED_RULES]
    for path in files + rules:
        require_file(path, root)
    budget(root / "AGENTS.md", root, "root")
    root_bytes = (root / "AGENTS.md").stat().st_size
    routers = discover_routers(root)
    for router in routers:
        if router != root / "AGENTS.md":
            budget(router, root, "nested")
            combined = root_bytes + router.stat().st_size
            if combined > COMBINED_ROUTER_BYTES:
                fail(
                    f"{rel(router, root)} with AGENTS.md exceeds "
                    f"{COMBINED_ROUTER_BYTES} bytes: {combined}"
                )
    for rule in rules:
        budget(rule, root, "adapter")
        validate_frontmatter(rule, root)
    if text(root / "CLAUDE.md").strip() != "@AGENTS.md":
        fail("CLAUDE.md must contain only @AGENTS.md")
    counts = validate_skills(root, routers)
    canonical = sorted((root / ".agents/skills").glob("*/SKILL.md"))
    adapters = sorted((root / ".claude/skills").glob("*/SKILL.md"))
    validate_links([*files, *rules, *routers, *canonical, *adapters], root)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        counts = validate_repository(args.root.resolve())
    except (OSError, GovernanceError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Governance verification: PASS ({counts[0]} Skills, {counts[1]} adapters, {counts[2]} routers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
