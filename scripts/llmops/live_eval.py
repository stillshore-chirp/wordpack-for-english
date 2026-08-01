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
    from scripts.llmops.estimate_run import estimate
except ModuleNotFoundError:  # direct script execution
    from estimate_run import estimate

CONFIRM_PHRASE = "RUN_PAID_LIVE_EVALUATION"


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


def main() -> int:
    args = _arguments()
    preflight = estimate(
        args.cases_file,
        max_cases=args.max_cases,
        max_requests=args.max_requests,
        max_output_tokens=args.max_output_tokens,
    )
    report: dict[str, object] = {"mode": args.mode, "preflight": preflight, "results": []}
    if args.mode == "estimate":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if args.confirm != CONFIRM_PHRASE:
        raise SystemExit(f"live mode requires --confirm {CONFIRM_PHRASE}")
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is required only for live mode")

    from backend.config import settings
    from backend.infrastructure.llm.json_response_parser import parse_json_response
    from backend.infrastructure.llm.prompts.examples import build_examples_prompt
    from backend.infrastructure.llm.prompts.wordpack import build_wordpack_prompt
    from backend.llmops import complete_typed, prompt_identity_from_builder
    from backend.llmops.completion import safe_provenance, with_validation
    from backend.models.word import ExampleCategory, WordPack
    from backend.providers import get_llm_provider
    from evals.evaluators.contracts import evaluate_wordpack_payload

    cases = list(json.loads(args.cases_file.read_text(encoding="utf-8")).get("cases") or [])[: args.max_cases]
    requests = int(preflight["estimated_requests"])
    settings.llm_max_tokens = max(1, args.max_output_tokens // max(1, requests))
    llm = get_llm_provider()
    results: list[dict[str, object]] = []
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
        completion = complete_typed(llm, wordpack_prompt, identity=identity)
        try:
            payload = parse_json_response(completion.content)
            parse_ok = isinstance(payload, dict)
        except Exception:
            payload = {}
            parse_ok = False
        provenance = safe_provenance(with_validation(completion, parse=parse_ok))
        payload["lemma"] = lemma
        payload["llm_model"] = settings.llm_model
        payload["generation_provenance"] = [provenance] if provenance else []
        examples: dict[str, list[dict[str, object]]] = {}
        for category in ExampleCategory:
            prompt = build_examples_prompt(lemma, category, count)
            example_identity = prompt_identity_from_builder(
                prompt_id=f"wordpack.examples.{category.value.lower()}",
                operation=f"wordpack.examples.{category.value.lower()}",
                builder=build_examples_prompt,
                schema={"type": "array"},
                major_settings={"model": settings.llm_model, "category": category.value, "count": count},
            )
            example_result = complete_typed(llm, prompt, identity=example_identity)
            try:
                parsed = parse_json_response(example_result.content, prefer_json_object=False)
                rows = parsed.get("examples", []) if isinstance(parsed, dict) else parsed
                rows = rows if isinstance(rows, list) else []
            except Exception:
                rows = []
            example_provenance = safe_provenance(with_validation(example_result, parse=bool(rows)))
            examples[category.value] = [
                {
                    **row,
                    "category": category.value,
                    "llm_model": settings.llm_model,
                    "generation_provenance": [example_provenance] if example_provenance else [],
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
        results.append({"case_id": case["case_id"], "passed": not findings, "findings": findings})
    report["results"] = results
    report["paid_llm_requests"] = requests
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
