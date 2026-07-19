from __future__ import annotations

from ...config import settings
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
            out: str = llm.complete(prompt)  # type: ignore[attr-defined]
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
