from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _builder_source(builder: Callable[..., Any] | str) -> str:
    if isinstance(builder, str):
        return builder
    try:
        return inspect.getsource(builder)
    except (OSError, TypeError):
        return (
            f"{getattr(builder, '__module__', '')}:"
            f"{getattr(builder, '__qualname__', repr(builder))}"
        )


@dataclass(frozen=True)
class PromptIdentity:
    """入力値に依存せず Git 上の prompt/schema/config を識別する。"""

    prompt_id: str
    prompt_revision: str
    schema_revision: str
    operation: str
    requested_parameters: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def prompt_identity_from_builder(
    *,
    prompt_id: str,
    operation: str,
    builder: Callable[..., Any] | str,
    schema: Mapping[str, Any] | str | None,
    major_settings: Mapping[str, Any] | None = None,
) -> PromptIdentity:
    """builder source と schema から手動 version 更新不要の identity を作る。"""

    normalized_schema: Any = schema or {"type": "text"}
    schema_revision = _sha256(normalized_schema)
    settings_payload = dict(major_settings or {})
    prompt_revision = _sha256(
        {
            "prompt_id": prompt_id,
            "operation": operation,
            "builder_source": _builder_source(builder),
            "schema_revision": schema_revision,
            "major_settings": settings_payload,
        }
    )
    return PromptIdentity(
        prompt_id=prompt_id,
        prompt_revision=prompt_revision,
        schema_revision=schema_revision,
        operation=operation,
        requested_parameters=settings_payload,
    )
