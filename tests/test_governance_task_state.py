from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scripts.validate_governance import GovernanceError, TASK_STATE_TEMPLATE, validate_task_state


ROOT = Path(__file__).resolve().parents[1]


def _template() -> dict[str, object]:
    return json.loads((ROOT / TASK_STATE_TEMPLATE).read_text(encoding="utf-8"))


def _write_state(tmp_path: Path, state: dict[str, object]) -> Path:
    path = tmp_path / "task-state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    return path


def test_task_state_template_is_valid_synthetic_and_client_neutral(tmp_path: Path) -> None:
    state = _template()

    assert state["completed_evidence"][0]["result"] == "pass"
    assert state["completed_evidence"][0]["artifact_reference"] in state["input_closure"]["artifacts"]
    assert state["invalidated_gates"] == []
    assert state["remaining_work"]
    serialized = json.dumps(state, ensure_ascii=False).casefold()
    assert not any(term in serialized for term in ("codex", "claude", "cursor", "client", "api"))
    assert "/users/" not in serialized
    assert re.search(r"\b[0-9a-f]{40}\b", serialized) is None

    validate_task_state(ROOT / TASK_STATE_TEMPLATE)
    state["completed_evidence"][0]["artifact_reference"] = None
    validate_task_state(_write_state(tmp_path, state), tmp_path)


@pytest.mark.parametrize("field,value", [("schema", "task-state/v2"), ("status", "unknown")])
def test_task_state_rejects_unknown_schema_or_status(
    tmp_path: Path, field: str, value: str
) -> None:
    state = _template()
    state[field] = value

    with pytest.raises(GovernanceError):
        validate_task_state(_write_state(tmp_path, state), tmp_path)


def test_task_state_rejects_missing_required_field(tmp_path: Path) -> None:
    state = _template()
    del state["remaining_work"]

    with pytest.raises(GovernanceError):
        validate_task_state(_write_state(tmp_path, state), tmp_path)


def test_task_state_rejects_unknown_evidence_result(tmp_path: Path) -> None:
    state = _template()
    state["completed_evidence"][0]["result"] = "unknown"

    with pytest.raises(GovernanceError):
        validate_task_state(_write_state(tmp_path, state), tmp_path)
