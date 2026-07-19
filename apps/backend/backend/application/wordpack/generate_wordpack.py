"""Compatibility exports for the legacy application import path.

New code should import the outer LLM adapter from
`backend.infrastructure.llm.wordpack_generator`.
"""

from __future__ import annotations

from ...infrastructure.llm.wordpack_generator import (
    build_llm_info,
    get_override_value,
    run_wordpack_flow,
)

__all__ = ["build_llm_info", "get_override_value", "run_wordpack_flow"]
