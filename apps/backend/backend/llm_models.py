from __future__ import annotations

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
        return options
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
        return options
    selected = str(verbosity).strip()
    if selected not in SUPPORTED_TEXT_VERBOSITIES:
        allowed = ", ".join(SUPPORTED_TEXT_VERBOSITIES)
        raise ValueError(
            f"Unsupported text verbosity: {selected}. Allowed values: {allowed}"
        )
    return {**options, "verbosity": selected}
