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


def _dependency_definition(value: Any, seen: set[str]) -> Any:
    if inspect.isfunction(value) or inspect.ismethod(value):
        return _callable_definition(value, seen)
    if inspect.isclass(value):
        return {
            "kind": "class",
            "name": f"{value.__module__}.{value.__qualname__}",
            "source": _builder_source(value),
        }
    if inspect.ismodule(value):
        return {"kind": "module", "name": value.__name__}
    if isinstance(value, Mapping):
        items = [
            (
                _dependency_definition(key, seen),
                _dependency_definition(item, seen),
            )
            for key, item in value.items()
        ]
        return {
            "kind": "mapping",
            "items": sorted(items, key=lambda pair: _canonical_json(pair[0])),
        }
    if isinstance(value, (list, tuple)):
        return [_dependency_definition(item, seen) for item in value]
    if isinstance(value, (set, frozenset)):
        items = [_dependency_definition(item, seen) for item in value]
        return sorted(items, key=_canonical_json)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return {
        "kind": "value",
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "value": str(value),
    }


def _callable_definition(builder: Callable[..., Any], seen: set[str]) -> dict[str, Any]:
    reference = (
        f"{getattr(builder, '__module__', '')}."
        f"{getattr(builder, '__qualname__', repr(builder))}"
    )
    if reference in seen:
        return {"kind": "callable_ref", "name": reference}
    seen.add(reference)
    dependencies: dict[str, Any] = {}
    try:
        closure = inspect.getclosurevars(builder)
        referenced = {**closure.globals, **closure.nonlocals}
        dependencies = {
            name: _dependency_definition(value, seen)
            for name, value in sorted(referenced.items())
        }
    except (TypeError, ValueError):
        # Some callable objects do not expose closure variables; their source still identifies them.
        pass
    return {
        "kind": "callable",
        "name": reference,
        "source": _builder_source(builder),
        "defaults": _dependency_definition(getattr(builder, "__defaults__", None), seen),
        "keyword_defaults": _dependency_definition(
            getattr(builder, "__kwdefaults__", None), seen
        ),
        "dependencies": dependencies,
    }


def _builder_definition(builder: Callable[..., Any] | str) -> Any:
    if isinstance(builder, str):
        return {"kind": "literal", "source": builder}
    return _callable_definition(builder, set())


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
    """builder と参照先の定義、schema から手動更新不要の identity を作る。"""

    normalized_schema: Any = schema or {"type": "text"}
    schema_revision = _sha256(normalized_schema)
    settings_payload = dict(major_settings or {})
    prompt_revision = _sha256(
        {
            "prompt_id": prompt_id,
            "operation": operation,
            "builder_definition": _builder_definition(builder),
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
