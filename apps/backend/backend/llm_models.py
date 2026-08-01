from __future__ import annotations

from typing import Mapping

SUPPORTED_LLM_MODELS: tuple[str, ...] = ("gpt-5.6-luna",)
DEFAULT_LLM_MODEL = SUPPORTED_LLM_MODELS[0]

SUPPORTED_REASONING_EFFORTS: tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)
DEFAULT_REASONING_EFFORT = "high"

SUPPORTED_TEXT_VERBOSITIES: tuple[str, ...] = ("low", "medium", "high")
DEFAULT_TEXT_VERBOSITY = "medium"


def effective_llm_generation_params(
    *,
    reasoning: object = None,
    text: object = None,
) -> str:
    """provider が実際に使う既定値を含む生成制御を安定表現へ正規化する。"""

    effort = DEFAULT_REASONING_EFFORT
    if isinstance(reasoning, Mapping):
        selected_effort = str(reasoning.get("effort") or "").strip()
        if selected_effort:
            effort = selected_effort
    verbosity = DEFAULT_TEXT_VERBOSITY
    if isinstance(text, Mapping):
        selected_verbosity = str(text.get("verbosity") or "").strip()
        if selected_verbosity:
            verbosity = selected_verbosity
    return f"reasoning.effort={effort};text.verbosity={verbosity}"


def ensure_supported_llm_model(model: str | None) -> str:
    selected = (model or DEFAULT_LLM_MODEL).strip()
    if selected not in SUPPORTED_LLM_MODELS:
        allowed = ", ".join(SUPPORTED_LLM_MODELS)
        raise ValueError(f"Unsupported LLM model: {selected}. Allowed models: {allowed}")
    return selected


def ensure_supported_reasoning_options(options: dict | None) -> dict | None:
    if options is None:
        return None
    effort = options.get("effort")
    if effort is None:
        return {**options, "effort": DEFAULT_REASONING_EFFORT}
    selected = str(effort).strip()
    if selected not in SUPPORTED_REASONING_EFFORTS:
        allowed = ", ".join(SUPPORTED_REASONING_EFFORTS)
        raise ValueError(
            f"Unsupported reasoning effort: {selected}. Allowed values: {allowed}"
        )
    return {**options, "effort": selected}


def ensure_supported_text_options(options: dict | None) -> dict | None:
    if options is None:
        return None
    verbosity = options.get("verbosity")
    if verbosity is None:
        return {**options, "verbosity": DEFAULT_TEXT_VERBOSITY}
    selected = str(verbosity).strip()
    if selected not in SUPPORTED_TEXT_VERBOSITIES:
        allowed = ", ".join(SUPPORTED_TEXT_VERBOSITIES)
        raise ValueError(
            f"Unsupported text verbosity: {selected}. Allowed values: {allowed}"
        )
    return {**options, "verbosity": selected}
