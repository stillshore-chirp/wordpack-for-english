from __future__ import annotations

from ...config import settings
from ...llmops.completion import complete_typed
from ...llmops.identity import prompt_identity_from_builder
from ...providers import get_llm_provider


class EmptyWordPackTitleGenerationError(RuntimeError):
    pass


def generate_sense_title_for_empty_wordpack(lemma: str) -> str | None:
    generated_title: str | None = None
    try:
        llm = get_llm_provider()
        prompt = (
            "次の英語の見出し語に対して、日本語の短い語義タイトルを1つだけ返してください。\n"
            "条件: 最大12文字、名詞句ベース、日本語のみ、説明文や引用符や記号は不要。\n"
            "見出し語: "
            f"{lemma}\n"
            "出力:"
        )
        try:
            identity = prompt_identity_from_builder(
                prompt_id="wordpack.empty_title",
                operation="wordpack.generate_empty_title",
                builder=generate_sense_title_for_empty_wordpack,
                schema={"type": "string", "maxLength": 20},
                major_settings={"model": settings.llm_model},
            )
            out = complete_typed(
                llm,
                prompt,
                identity=identity,
                response_mode="plain",
            ).content
        except Exception as exc:
            if settings.strict_mode:
                raise EmptyWordPackTitleGenerationError(
                    "LLM failed to generate sense_title (strict mode)"
                ) from exc
            out = ""
        cand = (out or "").strip().splitlines()[0] if isinstance(out, str) else ""
        cand = cand.strip().strip('"').strip("'")
        if cand:
            generated_title = cand[:20]
    except EmptyWordPackTitleGenerationError:
        raise
    except Exception:
        generated_title = None
    return generated_title
