from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from types import SimpleNamespace

import pytest

from backend.llmops.completion import (
    complete_typed,
    generation_workflow_context,
    provenance_from_result,
    runtime_correlation,
    safe_provenance,
)
from backend.llmops.types import CompletionResult
from backend.llmops.identity import prompt_identity_from_builder
from backend.providers import llm as provider_module


def _builder(value: str) -> str:
    return f"Prompt: {value}"


def _identity(operation: str = "test.operation"):
    return prompt_identity_from_builder(
        prompt_id="test.prompt",
        operation=operation,
        builder=_builder,
        schema={"type": "string"},
        major_settings={"model": "gpt-5.6-luna", "reasoning": {"effort": "high"}},
    )


def test_prompt_identity_is_input_independent_and_changes_with_schema() -> None:
    first = _identity()
    second = _identity()
    changed = prompt_identity_from_builder(
        prompt_id="test.prompt",
        operation="test.operation",
        builder=_builder,
        schema={"type": "object"},
        major_settings={"model": "gpt-5.6-luna", "reasoning": {"effort": "high"}},
    )
    assert first == second
    assert first.prompt_revision != changed.prompt_revision
    assert first.schema_revision != changed.schema_revision


def test_legacy_test_double_is_called_once_and_parallel_results_do_not_mix() -> None:
    class Echo:
        def complete(self, prompt: str) -> str:
            return prompt.upper()

    echo = Echo()

    def invoke(index: int):
        prompt = f"request-{index}"
        return complete_typed(echo, prompt, identity=_identity(f"operation-{index}"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(invoke, range(20)))

    assert [result.content for result in results] == [f"REQUEST-{index}" for index in range(20)]
    assert [result.prompt.operation for result in results if result.prompt] == [
        f"operation-{index}" for index in range(20)
    ]
    assert len({result.input_hash for result in results}) == 20
    assert len({result.output_hash for result in results}) == 20


def test_openai_typed_result_records_usage_fallback_and_store_false(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("Unsupported parameter: text.verbosity")
            return SimpleNamespace(
                output_text='{"ok": true}',
                id="resp-test",
                model="gpt-5.6-luna-resolved",
                status="completed",
                incomplete_details=None,
                usage=SimpleNamespace(
                    input_tokens=10,
                    input_tokens_details=SimpleNamespace(cached_tokens=4),
                    output_tokens=8,
                    output_tokens_details=SimpleNamespace(reasoning_tokens=3),
                    total_tokens=18,
                ),
            )

    class Client:
        def __init__(self, api_key: str) -> None:
            self.responses = Responses()

    monkeypatch.setattr(provider_module, "OpenAI", Client)
    monkeypatch.setattr(provider_module, "get_langfuse", lambda: None)
    provider = provider_module._OpenAILLM(
        api_key="fake",
        model="gpt-5.6-luna",
        reasoning={"effort": "high"},
        text={"verbosity": "medium"},
    )
    result = provider.complete_result("secret prompt", identity=_identity())

    assert len(calls) == 2
    assert all(call["store"] is False for call in calls)
    assert result.response_id == "resp-test"
    assert result.resolved_model == "gpt-5.6-luna-resolved"
    assert result.usage.cached_input_tokens == 4
    assert result.usage.reasoning_tokens == 3
    assert result.failed_profiles == ("json_with_controls",)
    assert result.fallback_reason == "PARAM_UNSUPPORTED"
    assert result.effective_parameters["profile"] == "json_without_optional_controls"


def test_bounded_provider_disables_all_physical_retry_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    client_options: list[dict[str, object]] = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            raise RuntimeError("Unsupported parameter: text.verbosity")

    class Client:
        def __init__(self, **kwargs) -> None:
            client_options.append(kwargs)
            self.responses = Responses()

    monkeypatch.setattr(provider_module, "OpenAI", Client)
    monkeypatch.setattr(provider_module, "get_langfuse", lambda: None)
    monkeypatch.setattr(provider_module.settings, "strict_mode", True)
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(provider_module, "_get_llm_executor", lambda: executor)
        provider = provider_module._OpenAILLM(
            api_key="fake",
            model="gpt-5.6-luna",
            reasoning={"effort": "high"},
            text={"verbosity": "medium"},
            allow_parameter_fallbacks=False,
            sdk_max_retries=0,
        )
        bounded = provider_module._llm_with_policy(provider, max_attempts=1)

        with pytest.raises(RuntimeError, match="typed completion failed"):
            bounded.complete_result("secret prompt", identity=_identity())

    assert len(calls) == 1
    assert client_options == [{"api_key": "fake", "max_retries": 0}]


def test_typed_attempt_count_accumulates_provider_and_policy_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    class Responses:
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise RuntimeError("temporary failure")
            if len(calls) == 2:
                raise RuntimeError("Unsupported parameter: text.verbosity")
            return SimpleNamespace(output_text='{"ok": true}', status="completed")

    class Client:
        def __init__(self, api_key: str) -> None:
            self.responses = Responses()

    monkeypatch.setattr(provider_module, "OpenAI", Client)
    monkeypatch.setattr(provider_module, "get_langfuse", lambda: None)
    monkeypatch.setattr(provider_module.settings, "strict_mode", True)
    monkeypatch.setattr(provider_module.settings, "llm_max_retries", 2)
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(provider_module, "_get_llm_executor", lambda: executor)
        provider = provider_module._OpenAILLM(
            api_key="fake",
            model="gpt-5.6-luna",
            reasoning={"effort": "high"},
            text={"verbosity": "medium"},
        )
        wrapped = provider_module._llm_with_policy(provider)

        result = wrapped.complete_result("secret prompt", identity=_identity())

    assert len(calls) == 3
    assert result.attempt_count == 3


def test_default_langfuse_payloads_contain_hashes_but_not_raw_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_module.settings, "langfuse_log_full_prompt", False)
    monkeypatch.setattr(provider_module.settings, "langfuse_log_full_output", False)
    input_payload = provider_module._prepare_span_input("model", "private prompt")
    assert input_payload["prompt_chars"] == len("private prompt")
    assert "prompt" not in input_payload
    assert "prompt_preview" not in input_payload

    observation = SimpleNamespace(updates=[])
    observation.update = lambda **kwargs: observation.updates.append(kwargs)
    provider_module._update_span_output(observation, "private output")
    output_payload = observation.updates[0]["output"]
    assert output_payload["content_chars"] == len("private output")
    assert "content" not in output_payload

    failing_observation = SimpleNamespace(
        update=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("send failed"))
    )
    provider_module._update_span_output(failing_observation, "private output")


def test_langfuse_initialization_failure_does_not_block_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    class Responses:
        def create(self, **_kwargs):
            return SimpleNamespace(output_text='{"ok": true}', status="completed")

    class Client:
        def __init__(self, api_key: str) -> None:
            self.responses = Responses()

    monkeypatch.setattr(provider_module, "OpenAI", Client)
    monkeypatch.setattr(
        provider_module,
        "get_langfuse",
        lambda: (_ for _ in ()).throw(RuntimeError("unavailable")),
    )
    provider = provider_module._OpenAILLM(
        api_key="fake",
        model="gpt-5.6-luna",
        reasoning={"effort": "high"},
        text={"verbosity": "medium"},
    )

    result = provider.complete_result("private prompt", identity=_identity())

    assert result.content == '{"ok": true}'
    assert result.response_status == "completed"


def test_provenance_never_contains_raw_content_and_serialization_failure_is_nonfatal() -> None:
    result = complete_typed(
        SimpleNamespace(complete=lambda prompt: "private output"),
        "private prompt",
        identity=_identity(),
    )
    provenance = provenance_from_result(result)
    serialized = str(provenance)
    assert "private prompt" not in serialized
    assert "private output" not in serialized

    class BrokenMapping(dict):
        def items(self):
            raise TypeError("boom")

    broken_result = replace(result, requested_parameters=BrokenMapping())
    assert safe_provenance(broken_result) is None


def test_oversized_provenance_is_reduced_below_hard_limit() -> None:
    result = CompletionResult(
        content="",
        provider="test",
        requested_model="gpt-5.6-luna",
        resolved_model="gpt-5.6-luna",
        requested_parameters={f"key-{index}": "x" * 1000 for index in range(40)},
        effective_parameters={f"key-{index}": "y" * 1000 for index in range(40)},
        failed_profiles=tuple("z" * 1000 for _ in range(40)),
        prompt=_identity(),
    )

    provenance = provenance_from_result(result)

    assert len(json.dumps(provenance).encode("utf-8")) <= 8192
    assert provenance["metadata_truncated"] is True


def test_workflow_correlation_is_context_local() -> None:
    with generation_workflow_context("job-a"):
        assert runtime_correlation()["workflow_id"] == "job-a"
    assert runtime_correlation()["workflow_id"] is None
