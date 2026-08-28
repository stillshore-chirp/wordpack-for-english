from __future__ import annotations

import re
from dataclasses import dataclass


_PROTECTED_DOT = "\u0000"
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
_ENGLISH_DOT_PATTERNS = (
    re.compile(r"(?<=\d)\.(?=\d)"),
    re.compile(r"\b(?:[A-Za-z]\.){2,}", re.IGNORECASE),
    re.compile(
        r"\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|St|vs|etc|No|e\.g|i\.e)\.",
        re.IGNORECASE,
    ),
    re.compile(r"(?<=[A-Za-z])\.(?=[A-Za-z])"),
)
_CLOSING_PUNCTUATION = frozenset('"\'”’)]}』」')


@dataclass(frozen=True)
class TranslationAlignmentIssue:
    reason: str
    paragraph_index: int | None
    english_paragraph_count: int
    japanese_paragraph_count: int
    english_sentence_count: int | None = None
    japanese_sentence_count: int | None = None


def split_paragraphs(text: str) -> list[str]:
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return [part.strip() for part in _PARAGRAPH_BREAK.split(normalized) if part.strip()]


def _protect_english_dots(text: str) -> str:
    protected = text
    for pattern in _ENGLISH_DOT_PATTERNS:
        protected = pattern.sub(
            lambda match: match.group(0).replace(".", _PROTECTED_DOT),
            protected,
        )
    return protected


def _split_sentences(
    text: str,
    *,
    terminators: frozenset[str],
    require_whitespace_after: bool,
) -> list[str]:
    source = str(text or "")
    if not source.strip():
        return []
    protected = _protect_english_dots(source) if "." in terminators else source
    sentences: list[str] = []
    start = 0
    index = 0
    while index < len(protected):
        if protected[index] not in terminators:
            index += 1
            continue
        end = index + 1
        while end < len(protected) and protected[end] in terminators:
            end += 1
        while end < len(protected) and protected[end] in _CLOSING_PUNCTUATION:
            end += 1
        if (
            not require_whitespace_after
            or end == len(protected)
            or protected[end].isspace()
        ):
            sentence = source[start:end].strip()
            if sentence:
                sentences.append(sentence)
            start = end
        index = end
    trailing = source[start:].strip()
    if trailing:
        sentences.append(trailing)
    return sentences


def split_english_sentences(text: str) -> list[str]:
    return _split_sentences(
        text,
        terminators=frozenset(".!?"),
        require_whitespace_after=True,
    )


def split_japanese_sentences(text: str) -> list[str]:
    return _split_sentences(
        text,
        terminators=frozenset("。！？!?"),
        require_whitespace_after=False,
    )


def translation_alignment_issue(
    body_en: str,
    body_ja: str,
) -> TranslationAlignmentIssue | None:
    english_paragraphs = split_paragraphs(body_en)
    japanese_paragraphs = split_paragraphs(body_ja)
    english_paragraph_count = len(english_paragraphs)
    japanese_paragraph_count = len(japanese_paragraphs)
    if english_paragraph_count != japanese_paragraph_count:
        return TranslationAlignmentIssue(
            reason="paragraph_count_mismatch",
            paragraph_index=None,
            english_paragraph_count=english_paragraph_count,
            japanese_paragraph_count=japanese_paragraph_count,
        )
    for paragraph_index, (english, japanese) in enumerate(
        zip(english_paragraphs, japanese_paragraphs, strict=True),
        start=1,
    ):
        english_sentence_count = len(split_english_sentences(english))
        japanese_sentence_count = len(split_japanese_sentences(japanese))
        if english_sentence_count != japanese_sentence_count:
            return TranslationAlignmentIssue(
                reason="sentence_count_mismatch",
                paragraph_index=paragraph_index,
                english_paragraph_count=english_paragraph_count,
                japanese_paragraph_count=japanese_paragraph_count,
                english_sentence_count=english_sentence_count,
                japanese_sentence_count=japanese_sentence_count,
            )
    return None


__all__ = [
    "TranslationAlignmentIssue",
    "split_english_sentences",
    "split_japanese_sentences",
    "split_paragraphs",
    "translation_alignment_issue",
]
