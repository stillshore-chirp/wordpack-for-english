from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from backend.models.word import WordPack

EXAMPLE_CATEGORIES = ("Dev", "CS", "LLM", "Business", "Common")


def _finding(code: str, message: str, *, operation: str) -> dict[str, str]:
    return {"code": code, "message": message, "operation": operation}


def _contains_lemma(text: str, lemma: str) -> bool:
    pattern = rf"(?<![A-Za-z0-9'-]){re.escape(lemma)}(?![A-Za-z0-9'-])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _validate_provenance(
    values: object, *, expected_model: str | None, operation: str
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    entries = values if isinstance(values, list) else []
    if not entries:
        return [_finding("provenance_missing", "generation provenance is required", operation=operation)]
    for item in entries:
        if not isinstance(item, Mapping):
            findings.append(_finding("provenance_invalid", "provenance must be an object", operation=operation))
            continue
        for key in ("prompt_id", "prompt_revision", "schema_revision", "operation", "input_hash", "output_hash"):
            if not str(item.get(key) or "").strip():
                findings.append(_finding("provenance_field_missing", f"{key} is required", operation=operation))
        resolved_model = str(item.get("resolved_model") or item.get("requested_model") or "")
        if expected_model and resolved_model and resolved_model != expected_model:
            findings.append(
                _finding(
                    "model_mismatch",
                    f"expected {expected_model}, got {resolved_model}",
                    operation=operation,
                )
            )
        validation = item.get("validation")
        if "validation" not in item:
            findings.append(
                _finding(
                    "validation_missing",
                    "provenance validation outcomes are required",
                    operation=operation,
                )
            )
        elif not isinstance(validation, Mapping):
            findings.append(
                _finding(
                    "validation_invalid",
                    "provenance validation must be an object",
                    operation=operation,
                )
            )
        else:
            missing_outcomes = [
                key for key in ("parse", "schema", "application") if key not in validation
            ]
            if missing_outcomes:
                findings.append(
                    _finding(
                        "validation_outcome_missing",
                        f"missing validation outcomes: {','.join(missing_outcomes)}",
                        operation=operation,
                    )
                )
            invalid_outcomes = [
                key
                for key in ("parse", "schema", "application")
                if key in validation and not isinstance(validation[key], bool)
            ]
            if invalid_outcomes:
                findings.append(
                    _finding(
                        "validation_outcome_invalid",
                        "validation outcomes must be boolean: "
                        + ",".join(invalid_outcomes),
                        operation=operation,
                    )
                )
            if validation.get("parse") is False:
                findings.append(
                    _finding(
                        "parse_failure",
                        "provenance classifies a parse failure",
                        operation=operation,
                    )
                )
            if validation.get("schema") is False:
                findings.append(
                    _finding(
                        "schema_failure",
                        "provenance classifies a generated-response schema failure",
                        operation=operation,
                    )
                )
            if validation.get("application") is False:
                findings.append(
                    _finding(
                        "application_failure",
                        "provenance classifies an unusable generated result",
                        operation=operation,
                    )
                )
        fallback_reason = str(item.get("fallback_reason") or "")
        if fallback_reason and fallback_reason not in {"PARAM_UNSUPPORTED", "PROVIDER_FAILURE"}:
            findings.append(_finding("fallback_unclassified", fallback_reason, operation=operation))
        serialized = json.dumps(item, ensure_ascii=False)
        if any(raw_key in item for raw_key in ("prompt", "input", "output", "content")):
            findings.append(_finding("raw_content_present", "provenance contains raw content", operation=operation))
        if len(serialized.encode("utf-8")) > 8192:
            findings.append(_finding("provenance_too_large", "provenance exceeds 8192 bytes", operation=operation))
    return findings


def evaluate_wordpack_payload(
    payload: Mapping[str, Any],
    *,
    expected_lemma: str,
    expected_model: str | None,
    expected_examples_per_category: int,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    try:
        wordpack = WordPack.model_validate(payload)
    except Exception as exc:
        error_count = getattr(exc, "error_count", lambda: None)()
        return [
            _finding(
                "schema_invalid",
                f"{type(exc).__name__}; error_count={error_count}",
                operation="wordpack",
            )
        ]
    if not wordpack.senses:
        findings.append(_finding("wordpack_senses_missing", "at least one sense is required", operation="wordpack"))
    findings.extend(
        _validate_provenance(
            wordpack.generation_provenance,
            expected_model=expected_model,
            operation="wordpack",
        )
    )
    seen: set[str] = set()
    for category in EXAMPLE_CATEGORIES:
        items = list(getattr(wordpack.examples, category))
        if len(items) != expected_examples_per_category:
            findings.append(
                _finding(
                    "example_count_mismatch",
                    f"{category}: expected {expected_examples_per_category}, got {len(items)}",
                    operation=f"examples.{category}",
                )
            )
        for item in items:
            operation = f"examples.{category}"
            if item.category is None or item.category.value != category:
                findings.append(_finding("category_mismatch", category, operation=operation))
            if not item.en.strip() or not item.ja.strip() or not (item.grammar_ja or "").strip():
                findings.append(
                    _finding(
                        "example_field_missing",
                        "en/ja/grammar_ja are required",
                        operation=operation,
                    )
                )
            word_count = len(re.findall(r"[A-Za-z]+(?:[-'][A-Za-z]+)*", item.en))
            if not 4 <= word_count <= 30:
                findings.append(_finding("example_word_count", str(word_count), operation=operation))
            if not _contains_lemma(item.en, expected_lemma):
                findings.append(_finding("lemma_missing", expected_lemma, operation=operation))
            normalized = " ".join(item.en.lower().split())
            if normalized in seen:
                findings.append(
                    _finding(
                        "duplicate_example",
                        "duplicate normalized example detected",
                        operation=operation,
                    )
                )
            seen.add(normalized)
            if expected_model and item.llm_model != expected_model:
                findings.append(_finding("model_mismatch", str(item.llm_model), operation=operation))
            findings.extend(
                _validate_provenance(
                    item.generation_provenance,
                    expected_model=expected_model,
                    operation=operation,
                )
            )
    return findings


def evaluate_fixture(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "case_id": path.stem,
            "passed": False,
            "findings": [
                _finding("json_parse_failed", str(exc), operation="fixture")
            ],
        }
    expected = raw.get("expected") or {}
    payload = raw.get("wordpack") or {}
    findings = evaluate_wordpack_payload(
        payload,
        expected_lemma=str(expected.get("lemma") or payload.get("lemma") or ""),
        expected_model=str(expected.get("model") or "") or None,
        expected_examples_per_category=int(expected.get("examples_per_category") or 0),
    )
    return {"case_id": str(raw.get("case_id") or path.stem), "passed": not findings, "findings": findings}
