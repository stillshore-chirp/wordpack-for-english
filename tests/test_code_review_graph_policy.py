from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.validate_code_review_graph_policy import (
    PolicyValidationError,
    load_fixture,
    validate_document,
    validate_fixture,
)


FIXTURE = Path("tests/fixtures/agent-harness/code-review-graph-policy.json")
DOCUMENT = Path("docs/agent-harness.md")


def _load() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_policy_document_and_representative_matrix_are_valid() -> None:
    validate_document(DOCUMENT.read_text(encoding="utf-8"))
    validate_fixture(_load())


@pytest.mark.parametrize("wrapper", ("html-comment", "fenced-code"))
def test_policy_document_rejects_hidden_or_fenced_section(wrapper: str) -> None:
    source = DOCUMENT.read_text(encoding="utf-8")
    start = source.index("### 変更影響調査の入口")
    end = source.index("\n## Hard gate", start)
    section = source[start:end].strip()
    if wrapper == "html-comment":
        replacement = f"<!--\n{section}\n-->"
    else:
        replacement = f"```md\n{section}\n```"
    hidden = source[:start] + replacement + source[end:]

    with pytest.raises(PolicyValidationError, match="visible"):
        validate_document(hidden)


def test_policy_document_rejects_peer_h3_before_required_policy() -> None:
    source = DOCUMENT.read_text(encoding="utf-8")
    heading_end = source.index("\n", source.index("### 変更影響調査の入口")) + 1
    peer_heading = "\n### Peer policy section\n\n"
    with_peer_heading = source[:heading_end] + peer_heading + source[heading_end:]

    with pytest.raises(PolicyValidationError, match="visible policy text"):
        validate_document(with_peer_heading)


@pytest.mark.parametrize(
    ("case_id", "mutation", "message"),
    (
        (
            "backend-logic-change",
            lambda case: case["graph_targets"].pop(),
            "graph_targets",
        ),
        (
            "copy-only",
            lambda case: case.update(route="graph"),
            "route must be skip",
        ),
        (
            "graph-analysis-failure",
            lambda case: case.update(fallback_targets=["rg"]),
            "fallback_targets",
        ),
    ),
)
def test_policy_matrix_rejects_routing_regressions(case_id: str, mutation, message: str) -> None:
    document = _load()
    case = deepcopy(next(item for item in document["cases"] if item["id"] == case_id))
    mutation(case)
    document["cases"] = [
        case if item["id"] == case_id else item for item in document["cases"]
    ]

    with pytest.raises(PolicyValidationError, match=message):
        validate_fixture(document)


def test_fixture_loader_reads_the_public_matrix() -> None:
    assert load_fixture(FIXTURE)["kind"] == "code-review-graph-routing-fixture"
