#!/usr/bin/env python3
"""Classify changed paths into gate-level evidence invalidations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import subprocess
from typing import Iterable, Sequence


BACKEND_FULL = "backend_full"
AGENT_HARNESS_FULL = "agent_harness_full"
AI_GOVERNANCE_FULL = "ai_governance_full"
WORKFLOW_CONTRACT = "workflow_contract"

FOCUSED_CONTRACT = "focused_contract_pytest"
YAML_PARSE = "workflow_yaml_parse"
BASE_HEAD_CLASSIFICATION = "base_head_classification"
LATEST_ACTIONS = "latest_actions"
WORKFLOW_YAML_EVIDENCE = "workflow_yaml"


@dataclass(frozen=True)
class GateInputs:
    paths: tuple[str, ...]
    config: tuple[str, ...]
    artifacts: tuple[str, ...]
    conditions: tuple[str, ...]


GATE_INPUTS = {
    BACKEND_FULL: GateInputs(
        ("apps/backend/backend/**", "tests/backend/**", "tests/integration/**"),
        ("requirements.txt", "pytest.ini", "firebase.json"),
        ("coverage summary",),
        ("Python matrix", "Firestore emulator"),
    ),
    AGENT_HARNESS_FULL: GateInputs(
        (
            "AGENTS.md",
            ".agents/**",
            "docs/agent-harness.md",
            "scripts/verify-agent-harness.sh", "scripts/validate_code_review_graph_policy.py",
            "tests/fixtures/agent-harness/code-review-graph-policy.json", "tests/test_code_review_graph_policy.py",
        ),
        ("requirements-agent-harness.txt",),
        ("verification summary",),
        ("Python 3.14", "CommonMark parser"),
    ),
    AI_GOVERNANCE_FULL: GateInputs(
        (
            "AGENTS.md",
            ".agents/**",
            "docs/agent-harness.md",
            "docs/ai-governance/**",
            ".github/ISSUE_TEMPLATE/**",
            ".github/pull_request_template.md",
            ".github/dependabot.yml",
            "scripts/verify-agent-harness.sh", "scripts/verify-ai-governance.sh",
            "scripts/validate_code_review_graph_policy.py", "tests/fixtures/agent-harness/code-review-graph-policy.json", "tests/test_code_review_graph_policy.py",
        ),
        ("requirements-agent-harness.txt",),
        ("governance summary",),
        ("Python 3.14", "CommonMark parser"),
    ),
    WORKFLOW_CONTRACT: GateInputs(
        (".github/workflows/**", "scripts/classify_*", "tests/test_*policy.py"),
        ("pytest.ini", "requirements-agent-harness.txt"),
        ("classifier JSON",),
        ("PR base...head", "latest Actions"),
    ),
}

BACKEND_PREFIXES = ("apps/backend/backend/", "tests/backend/", "tests/integration/")
BACKEND_FILES = {"requirements.txt", "pytest.ini", "firebase.json", ".env.ci", "Dockerfile.backend"}
WORKFLOW_PREFIX = ".github/workflows/"
WORKFLOW_CONTRACT_FILES = {
    "pytest.ini",
    "requirements-agent-harness.txt",
    "scripts/classify_ui_test_changes.py",
    "scripts/classify_verification_inputs.py",
    "tests/test_ui_test_change_classifier.py",
    "tests/test_github_actions_branch_policy.py",
    "tests/test_verification_inputs.py",
}
HARNESS_PREFIXES = (".agents/", ".claude/", ".cursor/")
HARNESS_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "docs/agent-harness.md",
    "docs/agent-principles.md",
    "docs/testing/index.md", "scripts/verify-agent-harness.sh", "scripts/validate_code_review_graph_policy.py",
    "scripts/classify_ui_test_changes.py", "scripts/classify_verification_inputs.py",
    "requirements-agent-harness.txt", "tests/test_github_actions_branch_policy.py",
    "tests/test_ui_test_change_classifier.py", "tests/test_verification_inputs.py", "tests/fixtures/agent-harness/code-review-graph-policy.json",
    "tests/test_code_review_graph_policy.py", ".github/workflows/agent-harness.yml",
}
AI_GOVERNANCE_FILES = {
    "requirements-agent-harness.txt",
    "scripts/verify-ai-governance.sh",
    ".github/pull_request_template.md",
    ".github/dependabot.yml",
}
AI_GOVERNANCE_PREFIXES = (".github/ISSUE_TEMPLATE/",)


@dataclass(frozen=True)
class GatePlan:
    invalidated_gates: tuple[str, ...]
    selected_checks: tuple[str, ...]
    retained_evidence: tuple[str, ...]
    fallback_reason: str | None
    changed_path_count: int
    unknown_path_count: int

    def as_json(self) -> dict[str, object]:
        return {
            "invalidated_gates": list(self.invalidated_gates),
            "selected_checks": list(self.selected_checks),
            "retained_evidence": list(self.retained_evidence),
            "fallback_reason": self.fallback_reason,
            "changed_path_count": self.changed_path_count,
            "unknown_path_count": self.unknown_path_count,
        }


def _normalize(path: str) -> str:
    return path.removeprefix("./")


def _is_backend(path: str) -> bool:
    return path in BACKEND_FILES or path.startswith(BACKEND_PREFIXES)


def _is_harness(path: str) -> bool:
    return path in HARNESS_FILES or path.startswith(HARNESS_PREFIXES)


def _is_ai_governance(path: str) -> bool:
    return path in AI_GOVERNANCE_FILES or path.startswith(AI_GOVERNANCE_PREFIXES)


def _is_known(path: str) -> bool:
    return (
        _is_backend(path)
        or _is_harness(path)
        or _is_ai_governance(path)
        or path in WORKFLOW_CONTRACT_FILES
        or path.startswith(WORKFLOW_PREFIX)
        or path.startswith("docs/")
    )


def classify_paths(
    paths: Iterable[str], *, fallback_reason: str | None = None
) -> GatePlan:
    changed = tuple(dict.fromkeys(_normalize(path) for path in paths if path))
    unknown = tuple(path for path in changed if not _is_known(path))
    fallback = fallback_reason
    if unknown and fallback is None:
        fallback = "unclassified path requires conservative verification"

    if fallback:
        invalidated = {BACKEND_FULL, AI_GOVERNANCE_FULL, WORKFLOW_CONTRACT}
        selected = {FOCUSED_CONTRACT, YAML_PARSE, BASE_HEAD_CLASSIFICATION, LATEST_ACTIONS}
        retained: set[str] = set()
    else:
        workflow_changed = any(path.startswith(WORKFLOW_PREFIX) for path in changed)
        contract_changed = any(path in WORKFLOW_CONTRACT_FILES for path in changed)
        invalidated = set()
        selected = set()
        retained = set() if workflow_changed else {WORKFLOW_YAML_EVIDENCE}
        if any(_is_backend(path) for path in changed):
            invalidated.add(BACKEND_FULL)
        if any(
            path.startswith("docs/ai-governance/") or _is_ai_governance(path)
            for path in changed
        ):
            invalidated.add(AI_GOVERNANCE_FULL)
        elif any(_is_harness(path) for path in changed):
            invalidated.add(AGENT_HARNESS_FULL)
        if workflow_changed or contract_changed:
            invalidated.add(WORKFLOW_CONTRACT)
            selected.add(FOCUSED_CONTRACT)
        if workflow_changed:
            selected.add(YAML_PARSE)
        if workflow_changed or contract_changed:
            selected.update({BASE_HEAD_CLASSIFICATION, LATEST_ACTIONS})

    return GatePlan(
        tuple(sorted(invalidated)),
        tuple(sorted(selected)),
        tuple(sorted(retained)),
        fallback,
        len(changed),
        len(unknown),
    )


def changed_paths(base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}", "--"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in result.stdout.split(b"\0")
        if item
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    try:
        plan = classify_paths(changed_paths(args.base, args.head))
    except subprocess.CalledProcessError as error:
        plan = classify_paths((), fallback_reason=f"git diff failed with status {error.returncode}")
    print(json.dumps(plan.as_json(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
