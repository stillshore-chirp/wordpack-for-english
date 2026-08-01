from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .identity import PromptIdentity


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class CompletionResult:
    """1回の論理 LLM invocation に閉じた並行安全な結果。"""

    content: str
    provider: str
    requested_model: str | None
    resolved_model: str | None
    requested_parameters: Mapping[str, Any] = field(default_factory=dict)
    effective_parameters: Mapping[str, Any] = field(default_factory=dict)
    fallback_profile: str | None = None
    fallback_reason: str | None = None
    failed_profiles: tuple[str, ...] = ()
    response_id: str | None = None
    response_status: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    latency_ms: int | None = None
    attempt_count: int = 1
    finish_info: str | None = None
    incomplete_info: str | None = None
    prompt: PromptIdentity | None = None
    request_id: str | None = None
    workflow_id: str | None = None
    trace_id: str | None = None
    release: str | None = None
    git_sha: str | None = None
    cloud_run_revision: str | None = None
    input_hash: str | None = None
    output_hash: str | None = None
    validation: Mapping[str, bool | None] = field(default_factory=dict)
