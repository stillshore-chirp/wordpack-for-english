#!/usr/bin/env python3
"""Check stable markers for the canonical subagent-orchestration block.

This checker validates marker placement and references only. Scenario meaning
remains in ``validate_agent_harness_scenarios.py`` and its existing fixture.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Iterable

from markdown_it import MarkdownIt


CONTRACT_PREFIX = "agent-harness:subagent-orchestration-contract:"
MARKER_IDS = tuple(f"{index:02d}" for index in range(1, 8))
SCENARIO_COVERAGE = {
    "01": "timeout-no-repeat",
    "02": "lane-liveness",
    "03": "lane-liveness",
    "04": "completed-agent",
    "05": "review-budget",
    "06": "focused-terminal",
    "07": "evidence-reuse",
}

# Reserved migration sentinel; it was never published and must remain absent.
RESERVED_DEPRECATED_SUFFIXES = ("deprecated",)

DIRECT_REACHABILITY = {
    "AGENTS.md": "docs/agent-harness.md",
    "README.md": "docs/agent-harness.md",
    ".claude/rules/agent-harness.md": "docs/agent-harness.md",
    ".cursor/rules/agent-harness.mdc": "docs/agent-harness.md",
    ".agents/skills/github-delivery/SKILL.md": "docs/agent-harness.md",
    "docs/ai-governance/03-evidence-and-completion-gates.md": "docs/agent-harness.md",
    "docs/ai-governance/13-maintenance-policy.md": "docs/agent-harness.md",
    "docs/ai-governance/15-agent-harness-compatibility.md": "docs/agent-harness.md",
}


def marker_comment(marker_id: str) -> str:
    return f"<!-- {CONTRACT_PREFIX}{marker_id} -->"


def contract_suffix(content: str) -> str | None:
    prefix = f"<!-- {CONTRACT_PREFIX}"
    if not content.startswith(prefix) or not content.endswith(" -->"):
        return None
    suffix = content[len(prefix) : -len(" -->")]
    if "\n" in content or not suffix:
        return "<malformed>"
    return suffix


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def tracked_paths(root: Path) -> Iterable[Path]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
        text=False,
    )
    for item in result.stdout.split(b"\0"):
        if item:
            path = root / os.fsdecode(item)
            try:
                if path.is_file():
                    yield path
            except OSError:
                continue


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def markdown_marker_counts(path: Path, text: str, comments: dict[str, str]) -> dict[str, int]:
    counts = {marker_id: 0 for marker_id in comments}
    for token in MarkdownIt("commonmark").parse(text):
        if token.type != "html_block":
            continue
        content = token.content.strip()
        for marker_id, comment in comments.items():
            if content == comment and "\n" not in content:
                counts[marker_id] += 1
    return counts


def marker_counts(root: Path, comments: dict[str, str]) -> dict[str, list[Path]]:
    locations = {marker_id: [] for marker_id in comments}
    markdown_suffixes = {".md", ".mdc", ".markdown"}
    for path in tracked_paths(root):
        text = read_text(path)
        if not text:
            continue
        if path.suffix.lower() in markdown_suffixes:
            counts = markdown_marker_counts(path, text, comments)
        else:
            counts = {
                marker_id: sum(line.strip() == comment for line in text.splitlines())
                for marker_id, comment in comments.items()
            }
        for marker_id, count in counts.items():
            locations[marker_id].extend([path] * count)
    return locations


def contract_marker_locations(root: Path) -> dict[str, list[Path]]:
    locations: dict[str, list[Path]] = {}
    markdown_suffixes = {".md", ".mdc", ".markdown"}
    prefix = f"<!-- {CONTRACT_PREFIX}"
    for path in tracked_paths(root):
        text = read_text(path)
        if not text:
            continue
        if path.suffix.lower() in markdown_suffixes:
            contents = (
                token.content.strip()
                for token in MarkdownIt("commonmark").parse(text)
                if token.type == "html_block"
            )
        else:
            contents = (line.strip() for line in text.splitlines())
        for content in contents:
            if not content.startswith(prefix):
                continue
            suffix = contract_suffix(content)
            if suffix is None or suffix == "<malformed>":
                fail(f"contract marker must be a single-line HTML comment: {path}")
            locations.setdefault(suffix, []).append(path)
    return locations


def canonical_markers(document: Path, comments: dict[str, str]) -> list[str]:
    source = read_text(document)
    if not source:
        fail(f"cannot read canonical document: {document}")
    tokens = MarkdownIt("commonmark").parse(source)
    headings = [
        index
        for index, token in enumerate(tokens[:-2])
        if token.type == "heading_open"
        and token.tag == "h2"
        and token.level == 0
        and tokens[index + 1].type == "inline"
        and tokens[index + 1].content == "Subagent orchestration"
        and tokens[index + 2].type == "heading_close"
    ]
    start = "<!-- agent-harness:subagent-orchestration:start -->"
    end = "<!-- agent-harness:subagent-orchestration:end -->"
    starts = [
        index
        for index, token in enumerate(tokens)
        if token.type == "html_block" and token.level == 0 and token.content.strip() == start
    ]
    ends = [
        index
        for index, token in enumerate(tokens)
        if token.type == "html_block" and token.level == 0 and token.content.strip() == end
    ]
    if len(headings) != 1 or len(starts) != 1 or len(ends) != 1:
        fail("canonical subagent-orchestration boundary is not unique")
    heading_index, start_index, end_index = headings[0], starts[0], ends[0]
    heading_map = tokens[heading_index].map
    start_map = tokens[start_index].map
    if (
        heading_map is None
        or start_map is None
        or start_map[0] != heading_map[1]
        or start_index <= heading_index + 2
        or end_index <= start_index
    ):
        fail("canonical boundary does not directly follow its heading")
    if any(
        token.type == "heading_open"
        and token.level == 0
        and token.tag in {"h1", "h2"}
        for token in tokens[start_index + 1 : end_index]
    ):
        fail("canonical block contains an inner H1 or H2")
    if end_index + 1 < len(tokens):
        next_token = tokens[end_index + 1]
        if not (
            next_token.type == "heading_open"
            and next_token.level == 0
            and next_token.tag in {"h1", "h2"}
        ):
            fail("canonical block end is not followed by a heading")

    found: list[str] = []
    for token in tokens[start_index + 1 : end_index]:
        if token.type == "html_block":
            content = token.content.strip()
            if content not in comments.values() or "\n" in content:
                fail("canonical block contains an unapproved inner HTML block")
            found.append(next(marker_id for marker_id, comment in comments.items() if comment == content))
        elif token.type == "inline":
            if any(child.type == "html_inline" for child in token.children or []):
                fail("canonical block contains an inline HTML marker")
    return found


def check_direct_reachability(root: Path) -> None:
    for relative, needle in DIRECT_REACHABILITY.items():
        path = root / relative
        if not path.is_file():
            fail(f"direct reachability source is missing: {relative}")
        if needle not in read_text(path):
            fail(f"{relative} must directly reference {needle}")


def check_scenario_coverage(root: Path, fixture: Path) -> None:
    if not fixture.is_file():
        fail(f"scenario fixture is missing: {fixture}")
    try:
        payload = json.loads(read_text(fixture))
        scenario_ids = {
            item["id"] for item in payload["scenarios"] if isinstance(item, dict) and "id" in item
        }
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        fail(f"scenario fixture cannot provide IDs: {error}")
    missing = sorted(set(SCENARIO_COVERAGE.values()) - scenario_ids)
    if missing:
        fail(f"stable marker mapping has no scenario contract: {', '.join(missing)}")
    validator = root / "scripts/validate_agent_harness_scenarios.py"
    if not validator.is_file():
        fail("existing scenario validator is missing")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    document = root / "docs/agent-harness.md"
    comments = {marker_id: marker_comment(marker_id) for marker_id in MARKER_IDS}

    found = canonical_markers(document, comments)
    if found != list(MARKER_IDS):
        fail(f"canonical marker order must be {', '.join(MARKER_IDS)}; found {', '.join(found) or '<none>'}")

    locations = marker_counts(root, comments)
    for marker_id, paths in locations.items():
        if len(paths) != 1 or paths[0] != document:
            rendered = ", ".join(str(path.relative_to(root)) for path in paths) or "<none>"
            fail(f"marker {marker_id} must be unique inside the canonical block; found at {rendered}")

    all_contract_markers = contract_marker_locations(root)
    for suffix, paths in all_contract_markers.items():
        if suffix in RESERVED_DEPRECATED_SUFFIXES:
            fail("reserved deprecated marker IDs must remain absent")
        if suffix not in MARKER_IDS:
            rendered = ", ".join(str(path.relative_to(root)) for path in paths)
            fail(f"unknown stable contract marker ID {suffix!r} at {rendered}")

    check_direct_reachability(root)
    check_scenario_coverage(root, args.fixture.resolve())
    print("stable subagent-orchestration markers: 7 ordered IDs, unique and reachable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
