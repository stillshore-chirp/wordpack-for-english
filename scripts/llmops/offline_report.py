#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "apps" / "backend"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

try:
    from scripts.llmops.cli_environment import prepare_backend_cli_environment
except ModuleNotFoundError:  # direct script execution
    from cli_environment import prepare_backend_cli_environment

prepare_backend_cli_environment()

from evals.evaluators.contracts import evaluate_fixture
from backend.domain.quiz.prompt_policy import build_quiz_generation_prompt
from backend.infrastructure.llm.generated_contracts import (
    GeneratedQuizPayload,
    GeneratedWordPackPayload,
)
from backend.infrastructure.llm.prompts.examples import (
    build_examples_prompt,
    examples_response_schema,
)
from backend.infrastructure.llm.prompts.wordpack import build_wordpack_prompt
from backend.llm_models import (
    DEFAULT_LLM_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TEXT_VERBOSITY,
)
from backend.llmops.identity import prompt_identity_from_builder
from backend.settings.base import Settings


def current_snapshot() -> dict[str, object]:
    identities = {
        "wordpack.core": prompt_identity_from_builder(
            prompt_id="wordpack.core",
            operation="wordpack.generate",
            builder=build_wordpack_prompt,
            schema=GeneratedWordPackPayload.model_json_schema(),
        ),
        "wordpack.examples": prompt_identity_from_builder(
            prompt_id="wordpack.examples",
            operation="wordpack.examples",
            builder=build_examples_prompt,
            schema=examples_response_schema(),
        ),
        "quiz.generate": prompt_identity_from_builder(
            prompt_id="quiz.generate",
            operation="quiz.generate",
            builder=build_quiz_generation_prompt,
            schema=GeneratedQuizPayload.model_json_schema(),
        ),
    }
    return {
        "prompt_revisions": {
            name: identity.prompt_revision for name, identity in identities.items()
        },
        "schema_revisions": {
            name: identity.schema_revision for name, identity in identities.items()
        },
        "model_profile": {
            "model": DEFAULT_LLM_MODEL,
            "reasoning_effort": DEFAULT_REASONING_EFFORT,
            "text_verbosity": DEFAULT_TEXT_VERBOSITY,
            "max_output_tokens": Settings.model_fields["llm_max_tokens"].default,
        },
    }


def build_report(
    fixtures_dir: Path,
    baseline_path: Path = Path("evals/baselines/offline-summary.json"),
) -> dict[str, object]:
    cases = [evaluate_fixture(path) for path in sorted(fixtures_dir.glob("*.json"))]
    regressions = sum(len(case["findings"]) for case in cases)
    snapshot = current_snapshot()
    try:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception:
        baseline = {}
    return {
        "prompt_changed": "Yes" if baseline.get("prompt_revisions") != snapshot["prompt_revisions"] else "No",
        "model_profile_changed": "Yes" if baseline.get("model_profile") != snapshot["model_profile"] else "No",
        "schema_changed": "Yes" if baseline.get("schema_revisions") != snapshot["schema_revisions"] else "No",
        "offline_contract_tests": "Passed" if regressions == 0 and cases else "Failed",
        "fixture_regressions": regressions,
        "paid_llm_requests": 0,
        "snapshot": snapshot,
        "cases": cases,
    }


def render_markdown(report: dict[str, object]) -> str:
    return "\n".join(
        [
            "## LLM change summary",
            "",
            f"- Prompt changed: {report['prompt_changed']}",
            f"- Model profile changed: {report['model_profile_changed']}",
            f"- Schema changed: {report['schema_changed']}",
            f"- Offline contract tests: {report['offline_contract_tests']}",
            f"- Fixture regressions: {report['fixture_regressions']}",
            "- Paid LLM requests: 0",
        ]
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic offline LLM contract evaluation")
    parser.add_argument("--fixtures-dir", type=Path, default=Path("evals/fixtures"))
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--summary-file", type=Path)
    args = parser.parse_args()
    report = build_report(args.fixtures_dir)
    markdown = render_markdown(report)
    print(markdown, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_output:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(markdown, encoding="utf-8")
    if args.summary_file:
        with args.summary_file.open("a", encoding="utf-8") as stream:
            stream.write(markdown)
    return 0 if report["offline_contract_tests"] == "Passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
