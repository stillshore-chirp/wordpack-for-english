#!/usr/bin/env python3
"""Classify changed paths into verification gates.

The classifier is deliberately data driven: every stable path family is a
``PathRule`` with a category, risk, and the gates it can invalidate.  Runtime
roots have a conservative fallback rule, while paths outside registered roots
fail closed so a new path cannot silently escape verification.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import subprocess
from typing import Iterable, Sequence


# Evidence-plan names are retained for callers which consume the non-UI part
# of the classifier.  The boolean fields below are the workflow interface.
BACKEND_FULL = "backend_full"
AGENT_HARNESS_FULL = "agent_harness_full"
AI_GOVERNANCE_FULL = "ai_governance_full"
WORKFLOW_CONTRACT = "workflow_contract"

FOCUSED_CONTRACT = "focused_contract_pytest"
YAML_PARSE = "workflow_yaml_parse"
BASE_HEAD_CLASSIFICATION = "base_head_classification"
LATEST_ACTIONS = "latest_actions"
WORKFLOW_YAML_EVIDENCE = "workflow_yaml"

OUTPUT_FIELDS = (
    "backend",
    "frontend",
    "backend_container",
    "deploy_preflight",
    "governance",
    "workflow_contract",
    "playwright_smoke",
    "playwright_visual",
    "classification_ok",
)

UI_GATES = frozenset({"playwright_smoke", "playwright_visual"})
ALL_GATES = frozenset(
    {
        "backend",
        "frontend",
        "backend_container",
        "deploy_preflight",
        "governance",
        "workflow_contract",
        "playwright_smoke",
        "playwright_visual",
    }
)


@dataclass(frozen=True)
class GateInputs:
    """Input closure retained for the evidence planner."""

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
            "scripts/validate_governance.py",
            "scripts/validate_agent_frontmatter.py",
            "scripts/verify_task_skills.py",
            "scripts/measure_effective_instruction_budget.py",
            "tests/test_agent_harness_budget.py",
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
            "scripts/validate_governance.py",
            "scripts/validate_agent_frontmatter.py",
            "scripts/verify_task_skills.py",
            "scripts/measure_effective_instruction_budget.py",
            "tests/test_agent_harness_budget.py",
        ),
        ("requirements-agent-harness.txt",),
        ("governance summary",),
        ("Python 3.14", "CommonMark parser"),
    ),
    WORKFLOW_CONTRACT: GateInputs(
        (
            ".github/workflows/**",
            "scripts/classify_*",
            "tests/test_*policy.py",
            "tests/test_verification_inputs.py",
        ),
        ("pytest.ini", "requirements-agent-harness.txt"),
        ("classifier JSON",),
        ("PR base...head", "latest Actions"),
    ),
}


# These sets are public because the evidence tests use them to assert closure
# coverage.  Matching itself is performed by PATH_RULES below.
BACKEND_PREFIXES = ("apps/backend/backend/", "tests/backend/", "tests/integration/")
BACKEND_FILES = {
    "requirements.txt",
    "pytest.ini",
    "firebase.json",
    ".env.ci",
    "Dockerfile.backend",
}
WORKFLOW_PREFIX = ".github/workflows/"
WORKFLOW_GATES = frozenset(
    {
        "backend",
        "frontend",
        "backend_container",
        "deploy_preflight",
        "governance",
        "workflow_contract",
        "playwright_smoke",
        "playwright_visual",
    }
)
WORKFLOW_CONTRACT_FILES = {
    "pytest.ini",
    "scripts/classify_verification_inputs.py",
    "tests/test_github_actions_branch_policy.py",
    "tests/test_verification_inputs.py",
}
LEGACY_MIGRATION_FILES = {
    "scripts/classify_ui_test_changes.py",
    "tests/test_ui_test_change_classifier.py",
}
HARNESS_PREFIXES = (".agents/", ".claude/", ".cursor/")
HARNESS_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "docs/agent-harness.md",
    "docs/agent-principles.md",
    "docs/testing/index.md",
    "scripts/validate_governance.py",
    "scripts/validate_agent_frontmatter.py",
    "scripts/verify_task_skills.py",
    "scripts/measure_effective_instruction_budget.py",
    "requirements-agent-harness.txt",
    "tests/test_agent_harness_budget.py",
}
AI_GOVERNANCE_FILES = {
    "requirements-agent-harness.txt",
    "scripts/validate_governance.py",
    "scripts/validate_agent_frontmatter.py",
    "scripts/verify_task_skills.py",
    "scripts/measure_effective_instruction_budget.py",
    "tests/test_agent_harness_budget.py",
    ".github/pull_request_template.md",
    ".github/dependabot.yml",
}
AI_GOVERNANCE_PREFIXES = (".github/ISSUE_TEMPLATE/",)


@dataclass(frozen=True)
class PathRule:
    """Declarative path classification rule.

    A rule can use exact paths, prefixes, and/or suffixes.  Prefix and suffix
    constraints are combined, which makes asset families explicit without a
    large collection of one-off exclusions.
    """

    rule_id: str
    category: str
    risk: str
    gates: frozenset[str] = frozenset()
    exact: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        if self.exact and path in self.exact:
            return True
        if self.exact and not (self.prefixes or self.suffixes):
            return False
        if self.prefixes and not any(path.startswith(prefix) for prefix in self.prefixes):
            return False
        if self.suffixes and not any(path.endswith(suffix) for suffix in self.suffixes):
            return False
        return bool(self.prefixes or self.suffixes)


def _rule(
    rule_id: str,
    category: str,
    risk: str,
    *,
    gates: Iterable[str] = (),
    exact: Iterable[str] = (),
    prefixes: Iterable[str] = (),
    suffixes: Iterable[str] = (),
) -> PathRule:
    return PathRule(
        rule_id=rule_id,
        category=category,
        risk=risk,
        gates=frozenset(gates),
        exact=tuple(exact),
        prefixes=tuple(prefixes),
        suffixes=tuple(suffixes),
    )


# Order matters only where a path belongs to both a broad and a narrow family.
# Keep narrow workflow/governance rules before documentation/test skip rules.
PATH_RULES: tuple[PathRule, ...] = (
    _rule(
        "e2e_visual_snapshots",
        "playwright_visual",
        "visual",
        gates={"playwright_visual"},
        prefixes={"tests/e2e/visual.spec.ts-snapshots/"},
    ),
    _rule(
        "e2e_visual_spec",
        "playwright_visual",
        "visual",
        gates={"playwright_visual"},
        exact={"tests/e2e/visual.spec.ts"},
    ),
    _rule(
        "e2e_shared_harness",
        "playwright_shared",
        "ui_harness",
        gates=UI_GATES,
        exact={"tests/e2e/helpers.ts", "tests/e2e/playwright.config.ts"},
    ),
    _rule(
        "e2e_smoke_spec",
        "playwright_smoke",
        "smoke",
        gates={"playwright_smoke"},
        exact={
            "tests/e2e/auth.spec.ts",
            "tests/e2e/guest.spec.ts",
            "tests/e2e/wordpack-server-query.spec.ts",
            "tests/e2e/wordpack.spec.ts",
        },
    ),
    _rule(
        "e2e_registered_full_spec",
        "playwright_full",
        "full_e2e",
        exact={
            "tests/e2e/errors.spec.ts",
            "tests/e2e/quiz.spec.ts",
            "tests/e2e/shelves.spec.ts",
        },
    ),
    _rule(
        "workflow_smoke",
        "workflow",
        "smoke_workflow",
        gates=WORKFLOW_GATES,
        exact={".github/workflows/ci.yml"},
    ),
    _rule(
        "workflow_deploy",
        "workflow",
        "deploy_workflow",
        gates=WORKFLOW_GATES,
        prefixes={".github/workflows/deploy"},
    ),
    _rule(
        "workflow_preflight",
        "workflow",
        "deploy_workflow",
        gates=WORKFLOW_GATES,
        exact={".github/workflows/production-deploy-preflight.yml"},
    ),
    _rule(
        "workflow_other",
        "workflow",
        "workflow_contract",
        gates=WORKFLOW_GATES,
        prefixes={WORKFLOW_PREFIX},
    ),
    _rule(
        "legacy_ui_classifier_migration",
        "legacy_migration",
        "workflow_contract",
        gates={"workflow_contract"},
        exact=LEGACY_MIGRATION_FILES,
    ),
    _rule(
        "backend_pytest_config",
        "backend_config",
        "backend_config",
        gates={"backend", "workflow_contract"},
        exact={"pytest.ini"},
    ),
    _rule(
        "workflow_contract_files",
        "workflow_contract",
        "classifier_contract",
        gates={"workflow_contract"},
        exact=WORKFLOW_CONTRACT_FILES,
    ),
    _rule(
        "governance_skill",
        "skill",
        "governance",
        gates={"governance"},
        prefixes=(".agents/skills/", ".claude/skills/", ".cursor/skills/"),
    ),
    _rule(
        "governance_agent_skill",
        "agent",
        "governance",
        gates={"governance"},
        prefixes=HARNESS_PREFIXES,
    ),
    _rule(
        "governance_agent_docs",
        "governance",
        "governance",
        gates={"governance"},
        exact={
            "AGENTS.md",
            "CLAUDE.md",
            "OPERATIONS.md",
            "docs/agent-harness.md",
            "docs/agent-principles.md",
            "docs/testing/index.md",
            "apps/backend/AGENTS.md",
            "apps/frontend/AGENTS.md",
        },
    ),
    _rule(
        "governance_docs",
        "governance",
        "governance",
        gates={"governance"},
        prefixes=("docs/agent/", "docs/skill/", "docs/ai-governance/"),
    ),
    _rule(
        "governance_scripts",
        "governance",
        "governance",
        gates={"governance"},
        exact=(
            "scripts/validate_governance.py",
            "scripts/validate_agent_frontmatter.py",
            "scripts/verify_task_skills.py",
            "scripts/measure_effective_instruction_budget.py",
            "tests/test_agent_harness_budget.py",
            "requirements-agent-harness.txt",
            ".github/pull_request_template.md",
            ".github/dependabot.yml",
        ),
        prefixes=(".github/ISSUE_TEMPLATE/",),
    ),
    _rule(
        "governance_validation_prefixes",
        "governance",
        "governance",
        gates={"governance"},
        prefixes=("scripts/validate_", "scripts/verify-", "scripts/verify_"),
    ),
    _rule(
        "deploy_scripts",
        "deploy",
        "deploy",
        gates={"deploy_preflight"},
        prefixes=("scripts/deploy", "scripts/promote"),
    ),
    _rule(
        "deploy_configuration",
        "deploy",
        "deploy",
        gates={"deploy_preflight", "backend"},
        prefixes=("configs/cloud-run/",),
        exact={"firebase.json", "firestore.indexes.json"},
    ),
    _rule(
        "container_definition",
        "container",
        "container",
        gates={"backend_container"},
        exact={"Dockerfile.backend", "cloudbuild.backend.yaml", ".dockerignore"},
        prefixes=("Dockerfile", "docker/"),
    ),
    _rule(
        "dependency_backend",
        "dependency",
        "backend_dependency",
        gates={"backend", "backend_container"},
        exact={"requirements.txt"},
    ),
    _rule(
        "dependency_root_playwright",
        "dependency",
        "ui_dependency",
        gates=UI_GATES,
        exact={
            "package.json",
            "package-lock.json",
            "npm-shrinkwrap.json",
            "pnpm-lock.yaml",
            "yarn.lock",
        },
    ),
    _rule(
        "dependency_frontend",
        "dependency",
        "frontend_dependency",
        gates={"frontend"},
        exact={"apps/frontend/package.json", "apps/frontend/package-lock.json"},
    ),
    _rule(
        "shared_runtime",
        "shared_runtime",
        "shared_runtime",
        gates={
            "backend",
            "frontend",
            "backend_container",
            "playwright_smoke",
            "playwright_visual",
        },
        exact={".env.ci", ".nvmrc", "scripts/prepare-frontend-env.mjs"},
    ),
    _rule(
        "frontend_config",
        "frontend_config",
        "frontend_config",
        gates={"frontend"},
        exact={
            "apps/frontend/index.html",
            "apps/frontend/tsconfig.build.json",
            "apps/frontend/tsconfig.json",
            "apps/frontend/tsconfig.node.json",
            "apps/frontend/vite.config.ts",
        },
    ),
    _rule(
        "backend_config",
        "backend_config",
        "backend_config",
        gates={"backend"},
        exact={"pytest.ini", "firebase.json"},
        prefixes=("apps/backend/config/",),
    ),
    _rule(
        "backend_tests",
        "backend_test",
        "backend_test",
        gates={"backend"},
        prefixes=("tests/backend/", "tests/integration/"),
    ),
    _rule(
        "docs_non_runtime",
        "docs",
        "non_runtime",
        exact={
            ".env.example",
            "README.md",
            "SECURITY.md",
            "UserManual.md",
            "env.deploy.example",
            "env.example",
            "apps/frontend/.env.example",
        },
        prefixes=("docs/", "plans/", "終了済みor参考ドキュメント/"),
    ),
    _rule(
        "fixture_non_runtime",
        "test_only",
        "non_runtime",
        prefixes=("tests/fixtures/",),
    ),
    _rule(
        "generic_test_non_runtime",
        "test_only",
        "test_only",
        prefixes=("tests/",),
    ),
)


FRONTEND_SOURCE_PREFIX = "apps/frontend/src/"
FRONTEND_PUBLIC_PREFIX = "apps/frontend/public/"
BACKEND_RUNTIME_PREFIX = "apps/backend/backend/"
E2E_PREFIX = "tests/e2e/"
VISUAL_ASSET_SUFFIXES = (
    ".avif",
    ".css",
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".less",
    ".png",
    ".sass",
    ".scss",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
)


@dataclass(frozen=True)
class PathClassification:
    path: str
    rule_id: str
    category: str
    risk: str
    gates: frozenset[str]


def _normalize(path: str) -> str:
    return path.removeprefix("./")


def _is_frontend_test(path: str) -> bool:
    pure_path = PurePosixPath(path)
    return "__tests__" in pure_path.parts or any(
        marker in pure_path.name for marker in (".test.", ".spec.")
    )


def _classify_frontend_path(path: str) -> PathClassification | None:
    if path.startswith(FRONTEND_PUBLIC_PREFIX):
        if path.endswith(VISUAL_ASSET_SUFFIXES):
            return PathClassification(
                path,
                "frontend_visual_asset",
                "frontend_visual",
                "visual",
                frozenset({"frontend", "playwright_visual"}),
            )
        return None

    if not path.startswith(FRONTEND_SOURCE_PREFIX):
        return None

    if _is_frontend_test(path):
        return PathClassification(
            path,
            "frontend_unit_test",
            "frontend_test",
            "frontend_unit",
            frozenset({"frontend"}),
        )
    if path.endswith(".d.ts"):
        return PathClassification(
            path,
            "frontend_type_declaration",
            "frontend_type",
            "frontend_compile",
            frozenset({"frontend"}),
        )
    if path.endswith(".tsx"):
        return PathClassification(
            path,
            "frontend_visual_runtime",
            "frontend_visual",
            "visual",
            frozenset({"frontend", "playwright_smoke", "playwright_visual"}),
        )
    if path.endswith(VISUAL_ASSET_SUFFIXES):
        return PathClassification(
            path,
            "frontend_visual_asset",
            "frontend_visual",
            "visual",
            frozenset({"frontend", "playwright_visual"}),
        )
    if path.startswith(FRONTEND_SOURCE_PREFIX):
        # This is an intentional extension point: a new file under the
        # frontend runtime root remains smoke-scoped until a narrower rule is
        # added.  It is not silently treated as an unrelated unknown path.
        return PathClassification(
            path,
            "frontend_runtime_root",
            "frontend_runtime",
            "smoke",
            frozenset({"frontend", "playwright_smoke"}),
        )
    return None


def _classify_backend_path(path: str) -> PathClassification | None:
    if path.startswith(BACKEND_RUNTIME_PREFIX):
        return PathClassification(
            path,
            "backend_runtime_root",
            "backend_runtime",
            "backend_runtime",
            frozenset({"backend", "backend_container"}),
        )
    return None


def classify_path(path: str) -> PathClassification | None:
    """Return the first registered classification for one normalized path."""

    path = _normalize(path)
    if not path:
        return None

    # E2E has an explicit registry.  A new spec must be added to PATH_RULES;
    # generic tests/ fallback below must not make it look verified.
    if path.startswith(E2E_PREFIX):
        for rule in PATH_RULES:
            if rule.matches(path) and rule.rule_id.startswith("e2e_"):
                return PathClassification(
                    path, rule.rule_id, rule.category, rule.risk, rule.gates
                )
        return None

    frontend_classification = _classify_frontend_path(path)
    if frontend_classification is not None:
        return frontend_classification

    for rule in PATH_RULES:
        if rule.rule_id.startswith("e2e_"):
            continue
        if rule.matches(path):
            return PathClassification(
                path, rule.rule_id, rule.category, rule.risk, rule.gates
            )

    backend_classification = _classify_backend_path(path)
    if backend_classification is not None:
        return backend_classification

    return None


def _classify_path(path: str) -> PathClassification | None:
    """Private compatibility alias used by focused contract tests."""

    return classify_path(path)


def _is_backend(path: str) -> bool:
    classification = classify_path(path)
    return bool(classification and "backend" in classification.gates)


def _is_harness(path: str) -> bool:
    classification = classify_path(path)
    return bool(
        classification
        and classification.category in {"agent", "skill", "governance"}
    )


def _is_ai_governance(path: str) -> bool:
    classification = classify_path(path)
    return bool(classification and classification.category == "governance")


def _is_known(path: str) -> bool:
    return classify_path(path) is not None


@dataclass(frozen=True)
class GatePlan:
    invalidated_gates: tuple[str, ...]
    selected_checks: tuple[str, ...]
    retained_evidence: tuple[str, ...]
    fallback_reason: str | None
    changed_path_count: int
    unknown_path_count: int
    categories: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    unknown_paths: tuple[str, ...] = ()
    backend: bool = False
    frontend: bool = False
    backend_container: bool = False
    deploy_preflight: bool = False
    governance: bool = False
    workflow_contract: bool = False
    playwright_smoke: bool = False
    playwright_visual: bool = False
    classification_ok: bool = True
    path_classifications: tuple[PathClassification, ...] = ()

    def as_json(self) -> dict[str, object]:
        category_counts = Counter(item.category for item in self.path_classifications)
        risk_counts = Counter(item.risk for item in self.path_classifications)
        payload: dict[str, object] = {
            "invalidated_gates": list(self.invalidated_gates),
            "selected_checks": list(self.selected_checks),
            "retained_evidence": list(self.retained_evidence),
            "fallback_reason": self.fallback_reason,
            "changed_path_count": self.changed_path_count,
            "unknown_path_count": self.unknown_path_count,
            "unknown_paths": list(self.unknown_paths[:20]),
            "categories": list(self.categories),
            "category_counts": dict(sorted(category_counts.items())),
            "risks": list(self.risks),
            "risk_counts": dict(sorted(risk_counts.items())),
        }
        payload.update({field: bool(getattr(self, field)) for field in OUTPUT_FIELDS})
        return payload


def _full_plan(changed_path_count: int = 0) -> GatePlan:
    return GatePlan(
        invalidated_gates=(
            BACKEND_FULL,
            AGENT_HARNESS_FULL,
            AI_GOVERNANCE_FULL,
            WORKFLOW_CONTRACT,
        ),
        selected_checks=(
            FOCUSED_CONTRACT,
            YAML_PARSE,
            BASE_HEAD_CLASSIFICATION,
            LATEST_ACTIONS,
        ),
        retained_evidence=(),
        fallback_reason=None,
        changed_path_count=changed_path_count,
        unknown_path_count=0,
        categories=("full_profile",),
        risks=("full",),
        backend=True,
        frontend=True,
        backend_container=True,
        deploy_preflight=True,
        governance=True,
        workflow_contract=True,
        playwright_smoke=True,
        playwright_visual=True,
        classification_ok=True,
    )


def classify_paths(
    paths: Iterable[str],
    *,
    fallback_reason: str | None = None,
    profile: str = "pr",
) -> GatePlan:
    """Classify changed paths for the PR profile or the full main profile."""

    if profile == "full":
        return _full_plan()
    if profile != "pr":
        raise ValueError(f"unsupported classifier profile: {profile}")

    changed = tuple(dict.fromkeys(_normalize(path) for path in paths if path))
    classified: list[PathClassification] = []
    unknown: list[str] = []
    for path in changed:
        classification = classify_path(path)
        if classification is None:
            unknown.append(path)
            classified.append(
                PathClassification(
                    path, "unknown_path", "unknown", "unknown", frozenset()
                )
            )
        else:
            classified.append(classification)
    classifications = tuple(classified)
    unknown_tuple = tuple(unknown)
    if unknown_tuple and fallback_reason is None:
        fallback_reason = "unclassified path requires an explicit category rule"

    # Unknown/fallback selects no gate: classification_ok forces the workflow
    # to stop before any UI or runtime job can be treated as successful.
    gates = frozenset(
        gate for classification in classifications for gate in classification.gates
    )
    categories = tuple(sorted({item.category for item in classifications}))
    risks = tuple(sorted({item.risk for item in classifications}))
    classification_ok = not unknown_tuple and fallback_reason is None

    workflow_changed = any(item.category == "workflow" for item in classifications)
    contract_changed = any(
        "workflow_contract" in item.gates for item in classifications
    )
    invalidated: set[str] = set()
    selected: set[str] = set()
    retained: set[str] = set()

    if fallback_reason:
        invalidated = {BACKEND_FULL, AI_GOVERNANCE_FULL, WORKFLOW_CONTRACT}
        selected = {FOCUSED_CONTRACT, YAML_PARSE, BASE_HEAD_CLASSIFICATION, LATEST_ACTIONS}
    else:
        if "backend" in gates or "backend_container" in gates:
            invalidated.add(BACKEND_FULL)
        if any(item.category == "governance" for item in classifications):
            invalidated.add(AI_GOVERNANCE_FULL)
        if any(item.category in {"agent", "skill"} for item in classifications):
            invalidated.add(AGENT_HARNESS_FULL)
        if workflow_changed or contract_changed:
            invalidated.add(WORKFLOW_CONTRACT)
            selected.add(FOCUSED_CONTRACT)
            selected.update({BASE_HEAD_CLASSIFICATION, LATEST_ACTIONS})
        if any(item.category == "workflow" for item in classifications):
            selected.add(YAML_PARSE)
        if not workflow_changed:
            retained.add(WORKFLOW_YAML_EVIDENCE)

    return GatePlan(
        invalidated_gates=tuple(sorted(invalidated)),
        selected_checks=tuple(sorted(selected)),
        retained_evidence=tuple(sorted(retained)),
        fallback_reason=fallback_reason,
        changed_path_count=len(changed),
        unknown_path_count=len(unknown_tuple),
        categories=categories,
        risks=risks,
        unknown_paths=unknown_tuple[:20],
        backend="backend" in gates,
        frontend="frontend" in gates,
        backend_container="backend_container" in gates,
        deploy_preflight="deploy_preflight" in gates,
        governance="governance" in gates,
        workflow_contract="workflow_contract" in gates,
        playwright_smoke="playwright_smoke" in gates,
        playwright_visual="playwright_visual" in gates,
        classification_ok=classification_ok,
        path_classifications=classifications,
    )


def changed_paths(base: str, head: str) -> list[str]:
    """Return both sides of renames and deleted paths from a base/head diff."""

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
        stderr=subprocess.PIPE,
    )
    return [
        value.decode("utf-8", errors="surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    ]


def _write_github_outputs(output_path: Path, plan: GatePlan) -> None:
    with output_path.open("a", encoding="utf-8") as output:
        for field in OUTPUT_FIELDS:
            output.write(f"{field}={str(bool(getattr(plan, field))).lower()}\n")


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Base commit SHA or ref")
    parser.add_argument("--head", help="Head commit SHA or ref")
    parser.add_argument(
        "--profile",
        choices=("pr", "full"),
        default="pr",
        help="Use change-scoped PR classification or the full main profile",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Alias for --profile full; selects every major gate",
    )
    parser.add_argument(
        "--no-renames",
        action="store_true",
        help="Preserve old and new names when reading the base/head diff",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Append classifier booleans for a GitHub Actions step",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    profile = "full" if args.full else args.profile
    if profile == "full":
        plan = _full_plan()
    else:
        if not args.base or not args.head:
            raise SystemExit("--base and --head are required for the PR profile")
        try:
            plan = classify_paths(changed_paths(args.base, args.head))
        except subprocess.CalledProcessError as error:
            plan = classify_paths(
                (), fallback_reason=f"git diff failed with status {error.returncode}"
            )

    if args.github_output:
        _write_github_outputs(args.github_output, plan)
    print(json.dumps(plan.as_json(), ensure_ascii=False, sort_keys=True))
    return 0 if plan.classification_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
