from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from ...llm_models import (
    ensure_supported_llm_model,
    ensure_supported_reasoning_options,
    ensure_supported_text_options,
)


class ExamplesGenerateRequest(BaseModel):
    """例文追加生成のための任意パラメータ。"""

    model: Optional[str] = Field(default=None, description="LLMモデル名の上書き")
    reasoning: Optional[dict] = Field(default=None)
    text: Optional[dict] = Field(default=None)

    @field_validator("model")
    @classmethod
    def ensure_model_supported(cls, value: str | None) -> str | None:
        return ensure_supported_llm_model(value) if value else value

    @field_validator("reasoning")
    @classmethod
    def ensure_reasoning_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_reasoning_options(value)

    @field_validator("text")
    @classmethod
    def ensure_text_supported(cls, value: dict | None) -> dict | None:
        return ensure_supported_text_options(value)


class LemmaLookupResponse(BaseModel):
    found: bool = Field(..., description="lemma がDBに存在するか")
    id: Optional[str] = Field(default=None, description="WordPack ID（存在時）")
    lemma: Optional[str] = Field(
        default=None, description="保存されている lemma（正規化反映後）"
    )
    sense_title: Optional[str] = Field(
        default=None, description="語義タイトル（存在時）"
    )
