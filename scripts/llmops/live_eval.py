#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for import_root in (REPOSITORY_ROOT, REPOSITORY_ROOT / "apps" / "backend"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

try:
    from scripts.llmops.cli_environment import prepare_backend_cli_environment
    from scripts.llmops.estimate_run import estimate
except ModuleNotFoundError:  # direct script execution
    from cli_environment import prepare_backend_cli_environment
    from estimate_run import estimate

prepare_backend_cli_environment()

CONFIRM_PHRASE = "RUN_PAID_LIVE_EVALUATION"
EXAMPLE_CATEGORY_NAMES = (
    "Dev",
    "CS",
    "LLM",
    "Business",
    "Common",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("estimate", "live"), default="estimate")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--cases-file", type=Path, default=Path("evals/cases/live_smoke.json"))
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=6)
    parser.add_argument("--max-output-tokens", type=int, default=25000)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main(*, provider_factory=None) -> int:
    args = _arguments()
    preflight = estimate(
        args.cases_file,
        max_cases=args.max_cases,
        max_requests=args.max_requests,
        max_output_tokens=args.max_output_tokens,
    )
    report: dict[str, object] = {"mode": args.mode, "preflight": preflight, "results": []}
    if args.mode == "estimate":
        _write_report(args.output, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"live mode requires --confirm {CONFIRM_PHRASE}")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required only for live mode")

    from backend.config import settings
    from backend.infrastructure.llm.json_response_parser import parse_json_response
    from backend.infrastructure.llm.prompts.examples import (
        build_examples_prompt,
        examples_response_schema,
        is_valid_examples_response,
    )
    from backend.infrastructure.llm.prompts.wordpack import build_wordpack_prompt
    from backend.llmops import complete_typed, prompt_identity_from_builder
    from backend.llmops.completion import safe_provenance, with_validation
    from backend.models.word import ExampleCategory, WordPack
    from evals.evaluators.contracts import evaluate_wordpack_payload

    cases = list(json.loads(args.cases_file.read_text(encoding="utf-8")).get("cases") or [])[: args.max_cases]
    requests = int(preflight["estimated_requests"])
    settings.llm_max_tokens = args.max_output_tokens // max(1, requests)
    # Paid evaluation disables both provider profile fallbacks and policy retries.
    # Therefore one logical completion is exactly one physical API attempt, including
    # after a timeout where the in-flight request cannot be cancelled reliably.
    if provider_factory is None:
        from backend.providers import get_llm_provider

        provider_factory = get_llm_provider
    llm = provider_factory(single_attempt=True)
    paid_requests = 0
    reserved_output_tokens = 0

    def bounded_completion(prompt: str, *, identity):
        nonlocal paid_requests, reserved_output_tokens
        if paid_requests >= args.max_requests:
            raise RuntimeError("physical API request budget exhausted")
        next_reserved = reserved_output_tokens + settings.llm_max_tokens
        if next_reserved > args.max_output_tokens:
            raise RuntimeError("output token budget exhausted")
        paid_requests += 1
        reserved_output_tokens = next_reserved
        return complete_typed(llm, prompt, identity=identity)

    results: list[dict[str, object]] = []
    def persist_live_report(*, failure: BaseException | None = None) -> None:
        report["results"] = results
        report["paid_llm_requests"] = paid_requests
        report["reserved_output_tokens"] = reserved_output_tokens
        report["single_physical_attempt_per_completion"] = True
        if failure is not None:
            report["failure"] = {
                "stage": "live_evaluation",
                "error_type": type(failure).__name__,
            }
        _write_report(args.output, report)

    try:
        for case in cases:
            lemma = str(case["lemma"])
            count = int(case.get("examples_per_category") or 2)
            wordpack_prompt = build_wordpack_prompt(lemma)
            identity = prompt_identity_from_builder(
                prompt_id="wordpack.core",
                operation="wordpack.generate",
                builder=build_wordpack_prompt,
                schema=WordPack.model_json_schema(),
                major_settings={"model": settings.llm_model},
            )
            completion = bounded_completion(wordpack_prompt, identity=identity)
            payload: dict[str, object] = {}
            parse_ok = False
            schema_ok = False
            try:
                parsed_wordpack = parse_json_response(completion.content)
                if isinstance(parsed_wordpack, dict):
                    payload = parsed_wordpack
                    parse_ok = True
            except Exception:
                # Invalid generated JSON is a quality finding; the paid run continues
                # so the report preserves all bounded case results.
                pass
            if parse_ok:
                try:
                    WordPack.model_validate({**payload, "lemma": lemma})
                    schema_ok = True
                except Exception:
                    # Schema failures are recorded in provenance and evaluated below;
                    # they do not abort the remaining bounded requests.
                    pass
            application_ok = bool(
                schema_ok
                and isinstance(payload.get("senses"), list)
                and payload["senses"]
            )
            provenance = safe_provenance(
                with_validation(
                    completion,
                    parse=parse_ok,
                    schema=schema_ok,
                    application=application_ok,
                )
            )
            payload["lemma"] = lemma
            payload["llm_model"] = settings.llm_model
            payload["generation_provenance"] = [provenance] if provenance else []
            examples: dict[str, list[dict[str, object]]] = {}
            for category_name in EXAMPLE_CATEGORY_NAMES:
                category = ExampleCategory(category_name)
                prompt = build_examples_prompt(lemma, category, count)
                example_identity = prompt_identity_from_builder(
                    prompt_id=f"wordpack.examples.{category.value.lower()}",
                    operation=f"wordpack.examples.{category.value.lower()}",
                    builder=build_examples_prompt,
                    schema=examples_response_schema(),
                    major_settings={
                        "model": settings.llm_model,
                        "category": category.value,
                        "count": count,
                    },
                )
                example_result = bounded_completion(prompt, identity=example_identity)
                parsed: object = {}
                parse_ok = False
                try:
                    parsed = parse_json_response(
                        example_result.content, prefer_json_object=False
                    )
                    parse_ok = True
                except Exception:
                    # A malformed example response is reported as parse/schema failure
                    # while the bounded evaluation continues through other categories.
                    pass
                rows = parsed.get("examples", []) if isinstance(parsed, dict) else []
                rows = rows if isinstance(rows, list) else []
                schema_ok = is_valid_examples_response(parsed)
                example_provenance = safe_provenance(
                    with_validation(
                        example_result,
                        parse=parse_ok,
                        schema=schema_ok,
                        application=schema_ok and len(rows) == count,
                    )
                )
                examples[category.value] = [
                    {
                        **row,
                        "category": category.value,
                        "llm_model": settings.llm_model,
                        "generation_provenance": (
                            [example_provenance] if example_provenance else []
                        ),
                    }
                    for row in rows[:count]
                    if isinstance(row, dict)
                ]
            payload["examples"] = examples
            findings = evaluate_wordpack_payload(
                payload,
                expected_lemma=lemma,
                expected_model=settings.llm_model,
                expected_examples_per_category=count,
            )
            results.append(
                {
                    "case_id": case["case_id"],
                    "passed": not findings,
                    "findings": findings,
                }
            )
    except Exception as exc:
        persist_live_report(failure=exc)
        raise
    persist_live_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
