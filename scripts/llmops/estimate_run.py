#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

HARD_MAX_CASES = 5
HARD_MAX_REQUESTS = 30
HARD_MAX_OUTPUT_TOKENS = 150000
REQUESTS_PER_CASE = 6


def estimate(cases_file: Path, *, max_cases: int, max_requests: int, max_output_tokens: int) -> dict[str, int]:
    cases = list(json.loads(cases_file.read_text(encoding="utf-8")).get("cases") or [])
    if not 1 <= max_cases <= HARD_MAX_CASES:
        raise ValueError(f"max_cases must be between 1 and {HARD_MAX_CASES}")
    if not 1 <= max_requests <= HARD_MAX_REQUESTS:
        raise ValueError(f"max_requests must be between 1 and {HARD_MAX_REQUESTS}")
    if not 1 <= max_output_tokens <= HARD_MAX_OUTPUT_TOKENS:
        raise ValueError(f"max_output_tokens must be between 1 and {HARD_MAX_OUTPUT_TOKENS}")
    selected_cases = min(len(cases), max_cases)
    requests = selected_cases * REQUESTS_PER_CASE
    if requests > max_requests:
        raise ValueError(f"estimated requests {requests} exceed max_requests {max_requests}")
    return {
        "case_count": selected_cases,
        "estimated_requests": requests,
        "max_output_tokens": max_output_tokens,
        "paid_llm_requests": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases-file", type=Path, default=Path("evals/cases/live_smoke.json"))
    parser.add_argument("--max-cases", type=int, default=1)
    parser.add_argument("--max-requests", type=int, default=6)
    parser.add_argument("--max-output-tokens", type=int, default=25000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = estimate(
        args.cases_file,
        max_cases=args.max_cases,
        max_requests=args.max_requests,
        max_output_tokens=args.max_output_tokens,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
