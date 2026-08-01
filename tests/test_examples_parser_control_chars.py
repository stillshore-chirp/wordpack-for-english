import os
import sys
from pathlib import Path

import pytest


# Ensure backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "backend"))
os.environ.setdefault("STRICT_MODE", "false")

from backend.flows.word_pack import WordPackFlow  # noqa: E402
from backend.models.word import ExampleCategory  # noqa: E402


def test_parse_examples_json_sanitizes_control_chars():
    flow = WordPackFlow(llm=None)

    # LLM が出しがちな『改行や制御文字が文字列内に素で混入した JSON 風テキスト』
    raw = (
        "{\n"
        "  \"examples\": [\n"
        "    { \"en\": \"Line1\nLine2\x0b\", \"ja\": \"行1\n行2\" },\n"
        "    { \"en\": \"Clean\", \"ja\": \"きれい\" }\n"
        "  ]\n"
        "}"
    )

    parsed = flow._parse_examples_json(raw)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]["en"].startswith("Line1")
    # JSON ロード後は \n として復元される
    assert "\n" in parsed[0]["en"]


def test_generate_examples_with_control_chars_is_not_dropped():
    class FakeLLM:
        def complete(self, prompt: str) -> str:  # type: ignore[override]
            return (
                "{\n"
                "  \"examples\": [\n"
                "    { \"en\": \"A line\nwith newline\x0c\", \"ja\": \"例1\", "
                "\"grammar_ja\": \"文法解説1\" },\n"
                "    { \"en\": \"Second\", \"ja\": \"例2\", "
                "\"grammar_ja\": \"文法解説2\" }\n"
                "  ]\n"
                "}"
            )

    flow = WordPackFlow(llm=FakeLLM(), llm_info={"model": "test", "params": None})
    plan = {ExampleCategory.Dev: 2}
    out = flow.generate_examples_for_categories("reliability", plan)
    items = out.get(ExampleCategory.Dev, [])
    assert len(items) == 2
    assert items[0].en.startswith("A line")
    assert "\n" in items[0].en


def test_parse_examples_json_handles_broken_json_gracefully():
    flow = WordPackFlow(llm=None)

    # 文法的に壊れた JSON（LLM が途中までしか出力しなかった等）
    raw = "{ \"examples\": [ { \"en\": \"A\", \"ja\": \"あ\" }  INVALID"

    parsed = flow._parse_examples_json(raw)
    assert isinstance(parsed, list)
    assert parsed == []


def test_parse_examples_json_handles_invalid_shape_gracefully():
    flow = WordPackFlow(llm=None)

    # JSON としては正しいが期待スキーマと異なるケース
    raw = "{ \"foo\": 1 }"

    parsed = flow._parse_examples_json(raw)
    assert isinstance(parsed, list)
    assert parsed == []


