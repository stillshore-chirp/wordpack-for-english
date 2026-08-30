#!/usr/bin/env python3
"""Validate the shared code-review-graph impact-investigation contract.

The fixture is a small, public-safe routing matrix.  It checks that the
canonical document defines when graph analysis is useful, when it may be
skipped, and which existing reference-tracing path remains available when a
graph cannot provide a trustworthy result.  It deliberately does not encode
any product-specific command, provider, or client.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, NoReturn

from markdown_it import MarkdownIt


SCHEMA_VERSION = 1
EXPECTED_CASES = {
    "backend-logic-change": "graph",
    "frontend-shared-processing-change": "graph",
    "api-contract-change": "graph",
    "cross-layer-refactor": "graph",
    "documentation-only": "skip",
    "copy-only": "skip",
    "isolated-local-css": "skip",
    "combined-skip-scope": "graph",
    "graph-unavailable": "fallback",
    "graph-unconfigured": "fallback",
    "graph-stale": "fallback",
    "graph-analysis-failure": "fallback",
    "graph-insufficient-result": "fallback",
}
GRAPH_TARGETS = {
    "related-code",
    "callers",
    "boundaries",
    "test-candidates",
}
EXPECTED_FALLBACK_STATUSES = {
    "graph-unavailable": "unavailable",
    "graph-unconfigured": "unconfigured",
    "graph-stale": "stale",
    "graph-analysis-failure": "analysis-failure",
    "graph-insufficient-result": "insufficient-result",
}
FALLBACK_TARGETS = {"rg", "import/reference-tracing"}
SKIPPABLE_SCOPES = {"documentation-only", "copy-only", "isolated-local-css"}
GRAPH_SCOPES = {"nontrivial-code", "combined-skip-scope"}
REQUIRED_DOCUMENT_TEXT = (
    "code-review-graph",
    "実装前の影響範囲調査",
    "非自明なコード改修",
    "コード、呼び出し元、レイヤー境界・契約境界、テスト候補",
    "graphだけで影響範囲、安全性、テスト十分性を確定したり",
    "文書のみ、文言のみ、独立した局所CSSのみ",
    "利用不能、未設定、古い、解析失敗、情報不足",
    "rg、import追跡、参照追跡",
    "GitHub配送とレビュー収束の条件を変更しない",
)


class PolicyValidationError(ValueError):
    """Raised when the graph routing contract is incomplete or unsafe."""


def _fail(message: str) -> NoReturn:
    raise PolicyValidationError(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        _fail(message)


def _nonempty_string(value: Any, label: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty")
    return value


def _string_set(value: Any, label: str) -> set[str]:
    _require(isinstance(value, list) and bool(value), f"{label} must be a non-empty list")
    result: set[str] = set()
    for item in value:
        result.add(_nonempty_string(item, f"{label} item"))
    _require(len(result) == len(value), f"{label} must not contain duplicates")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return value


def _visible_section_text(document: str) -> str:
    """Return visible Markdown content under the canonical H3 section.

    CommonMark treats HTML comments and fenced code as non-visible blocks. An
    inline HTML token is skipped as a whole so hidden spans cannot contribute
    required policy text either.
    """

    tokens = MarkdownIt("commonmark").parse(document)
    headings = [
        index
        for index, token in enumerate(tokens[:-2])
        if token.type == "heading_open"
        and token.tag == "h3"
        and token.level == 0
        and tokens[index + 1].type == "inline"
        and tokens[index + 1].content == "変更影響調査の入口"
        and tokens[index + 2].type == "heading_close"
    ]
    _require(
        len(headings) == 1,
        "canonical document must contain one visible 変更影響調査の入口 heading",
    )
    start = headings[0] + 3
    end = len(tokens)
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token.type == "heading_open" and token.level == 0 and token.tag in {"h1", "h2", "h3"}:
            end = index
            break

    visible_lines: list[str] = []
    for token in tokens[start:end]:
        if token.type in {"html_block", "fence", "code_block"}:
            continue
        if token.type != "inline":
            continue
        children = token.children or []
        if any(child.type == "html_inline" for child in children):
            continue
        parts: list[str] = []
        for child in children:
            if child.type in {"text", "code_inline"}:
                parts.append(child.content)
            elif child.type in {"softbreak", "hardbreak"}:
                parts.append("\n")
            elif child.type == "image":
                parts.append(f" {child.content} ")
            elif child.content:
                parts.append(f" {child.content} ")
        visible_lines.append("".join(parts))
    return "\n".join(visible_lines)


def _validate_case(case: Any, index: int) -> None:
    label = f"case {index}"
    item = _mapping(case, label)
    case_id = _nonempty_string(item.get("id"), f"{label}.id")
    _require(case_id in EXPECTED_CASES, f"{label} has unknown id: {case_id}")
    _require(
        set(item)
        <= {
            "id",
            "scope",
            "paths",
            "route",
            "graph_status",
            "graph_targets",
            "fallback_targets",
            "skip_reason",
            "fallback_reason",
        },
        f"{label} contains unsupported fields",
    )
    scope = _nonempty_string(item.get("scope"), f"{label}.scope")
    _string_set(item.get("paths"), f"{label}.paths")
    route = _nonempty_string(item.get("route"), f"{label}.route")
    _require(route == EXPECTED_CASES[case_id], f"{label} route must be {EXPECTED_CASES[case_id]}")

    if route == "graph":
        _require(scope in GRAPH_SCOPES, f"{label} graph route must cover a graph scope")
        _require(
            item.get("graph_status", "available") == "available",
            f"{label} graph route needs an available graph",
        )
        _require(
            _string_set(item.get("graph_targets"), f"{label}.graph_targets")
            == GRAPH_TARGETS,
            f"{label} graph_targets must cover related code, callers, boundaries, "
            "and test candidates",
        )
        _require(
            "fallback_targets" not in item,
            f"{label} graph route must not encode fallback targets",
        )
        return

    if route == "skip":
        _require(scope in SKIPPABLE_SCOPES, f"{label} is not a representative skip scope")
        _require(
            "graph_status" not in item and "graph_targets" not in item,
            f"{label} skip route must not claim graph analysis",
        )
        _nonempty_string(item.get("skip_reason"), f"{label}.skip_reason")
        _require(
            "fallback_targets" not in item,
            f"{label} skip route must not claim fallback analysis",
        )
        return

    _require(route == "fallback", f"{label} has unsupported route: {route}")
    _require(scope == "nontrivial-code", f"{label} fallback must cover nontrivial-code")
    _require(
        item.get("graph_status") == EXPECTED_FALLBACK_STATUSES[case_id],
        f"{label} graph_status must be {EXPECTED_FALLBACK_STATUSES[case_id]}",
    )
    _require("graph_targets" not in item, f"{label} fallback must not claim graph targets")
    _require(
        _string_set(item.get("fallback_targets"), f"{label}.fallback_targets")
        == FALLBACK_TARGETS,
        f"{label} fallback_targets must use search and reference tracing",
    )
    _nonempty_string(item.get("fallback_reason"), f"{label}.fallback_reason")


def validate_document(document: str) -> None:
    visible_section = _visible_section_text(document)
    for required in REQUIRED_DOCUMENT_TEXT:
        _require(
            required in visible_section,
            f"canonical document must contain visible policy text: {required}",
        )


def validate_fixture(document: Mapping[str, Any]) -> None:
    _require(document.get("kind") == "code-review-graph-routing-fixture", "unexpected fixture kind")
    _require(document.get("schema_version") == SCHEMA_VERSION, "unsupported fixture schema version")
    cases = document.get("cases")
    _require(
        isinstance(cases, list) and len(cases) == len(EXPECTED_CASES),
        "fixture must contain the complete representative matrix",
    )
    seen: set[str] = set()
    for index, case in enumerate(cases):
        _validate_case(case, index)
        case_id = str(_mapping(case, f"case {index}").get("id"))
        _require(case_id not in seen, f"fixture repeats case id: {case_id}")
        seen.add(case_id)
    _require(
        seen == set(EXPECTED_CASES),
        "fixture case IDs do not match the required representative matrix",
    )


def load_fixture(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"cannot load fixture {path}: {error}")
    return _mapping(payload, "fixture")


def _self_test(fixture: Mapping[str, Any]) -> None:
    validate_fixture(fixture)
    cases = fixture["cases"]

    graph_case = next(case for case in cases if case["id"] == "backend-logic-change")
    broken_graph = dict(graph_case)
    broken_graph["graph_targets"] = ["related-code"]
    try:
        _validate_case(broken_graph, 0)
    except PolicyValidationError:
        pass
    else:
        _fail("self-test accepted incomplete graph targets")

    skip_case = next(case for case in cases if case["id"] == "copy-only")
    broken_skip = dict(skip_case)
    broken_skip["route"] = "graph"
    try:
        _validate_case(broken_skip, 0)
    except PolicyValidationError:
        pass
    else:
        _fail("self-test accepted graph routing for a representative skip case")

    fallback_case = next(case for case in cases if case["id"] == "graph-analysis-failure")
    broken_fallback = dict(fallback_case)
    broken_fallback["fallback_targets"] = ["rg"]
    try:
        _validate_case(broken_fallback, 0)
    except PolicyValidationError:
        pass
    else:
        _fail("self-test accepted an incomplete fallback")

    broken_status = dict(fallback_case)
    broken_status["graph_status"] = "stale"
    try:
        _validate_case(broken_status, 0)
    except PolicyValidationError:
        pass
    else:
        _fail("self-test accepted a mismatched fallback status")

    combined_case = next(case for case in cases if case["id"] == "combined-skip-scope")
    broken_combined = dict(combined_case)
    broken_combined["route"] = "skip"
    try:
        _validate_case(broken_combined, 0)
    except PolicyValidationError:
        pass
    else:
        _fail("self-test accepted skipping a combined scope")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("document", type=Path)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    validate_document(args.document.read_text(encoding="utf-8"))
    fixture = load_fixture(args.fixture)
    validate_fixture(fixture)
    if args.self_test:
        _self_test(fixture)
    print(
        f"code-review-graph policy verification: PASS "
        f"({len(fixture['cases'])} representative cases)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PolicyValidationError) as error:
        raise SystemExit(f"ERROR: {error}") from error
