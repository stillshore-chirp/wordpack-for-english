from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "backend"))

from backend.llm_models import (  # noqa: E402
    DEFAULT_LLM_MODEL,
    DEFAULT_REASONING_EFFORT,
    DEFAULT_TEXT_VERBOSITY,
    SUPPORTED_LLM_MODELS,
    ensure_supported_llm_model,
    ensure_supported_reasoning_options,
    ensure_supported_text_options,
)
from backend.models.article import ArticleImportRequest  # noqa: E402
from backend.models.quiz import QuizGenerateRequest  # noqa: E402
from backend.models.word import WordPackRequest  # noqa: E402
from backend.settings.base import Settings  # noqa: E402


def test_luna_is_the_only_supported_model_and_high_is_the_default_effort():
    assert SUPPORTED_LLM_MODELS == ("gpt-5.6-luna",)
    assert DEFAULT_LLM_MODEL == "gpt-5.6-luna"
    assert DEFAULT_REASONING_EFFORT == "high"
    assert ensure_supported_llm_model(None) == "gpt-5.6-luna"


def test_high_reasoning_defaults_reserve_time_and_output_budget():
    assert Settings.model_fields["request_timeout_ms"].default == 60000
    assert Settings.model_fields["llm_timeout_ms"].default == 300000
    assert Settings.model_fields["llm_request_timeout_ms"].default == 1500000
    assert Settings.model_fields["llm_max_tokens"].default == 25000


def test_partial_reasoning_options_keep_the_high_application_default():
    assert ensure_supported_reasoning_options({"summary": "auto"}) == {
        "summary": "auto",
        "effort": DEFAULT_REASONING_EFFORT,
    }


def test_partial_text_options_keep_the_medium_application_default():
    assert ensure_supported_text_options({"format": {"type": "json_object"}}) == {
        "format": {"type": "json_object"},
        "verbosity": DEFAULT_TEXT_VERBOSITY,
    }


@pytest.mark.parametrize("model", ["gpt-5.4-mini", "gpt-5.4-nano"])
def test_legacy_models_are_rejected_for_new_requests(model: str):
    with pytest.raises(ValueError, match="Unsupported LLM model"):
        ensure_supported_llm_model(model)


@pytest.mark.parametrize(
    ("request_model", "payload"),
    [
        (WordPackRequest, {"lemma": "luna"}),
        (ArticleImportRequest, {"text": "Luna migration"}),
        (QuizGenerateRequest, {"lemmas": ["luna"]}),
    ],
)
def test_legacy_minimal_reasoning_is_rejected(request_model, payload):
    with pytest.raises(ValidationError, match="Unsupported reasoning effort"):
        request_model.model_validate(
            {
                **payload,
                "model": "gpt-5.6-luna",
                "reasoning": {"effort": "minimal"},
            }
        )


@pytest.mark.parametrize("effort", ["none", "low", "medium", "high", "xhigh", "max"])
def test_luna_reasoning_efforts_are_accepted(effort: str):
    request = WordPackRequest(
        lemma="luna",
        model="gpt-5.6-luna",
        reasoning={"effort": effort},
        text={"verbosity": "medium"},
    )
    assert request.reasoning == {"effort": effort}
