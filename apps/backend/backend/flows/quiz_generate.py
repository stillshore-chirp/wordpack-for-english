from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Mapping
from typing import Any

from ..application.wordpack.generate_wordpack import build_llm_info, get_override_value
from ..domain.quiz.prompt_policy import build_quiz_generation_prompt
from ..domain.wordpack.lemma import validate_lemma
from ..id_factory import generate_word_pack_id
from ..infrastructure.llm.json_response_parser import parse_json_response
from ..logging import logger
from ..models.quiz import Quiz, QuizGenerateRequest, QuizWordPackLink, QuizWordPackOccurrence
from ..providers import get_llm_provider


def generate_quiz_id() -> str:
    import uuid

    return f"quiz:{uuid.uuid4().hex}"


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


def _normalize_llm_params(req: QuizGenerateRequest) -> str | None:
    info = build_llm_info(req)
    params = info.get("params")
    return str(params) if params else None


def _complete_json(llm: object, prompt: str) -> str:
    complete = getattr(llm, "complete", None)
    if callable(complete):
        return str(complete(prompt) or "")
    complete_text = getattr(llm, "complete_text", None)
    if callable(complete_text):
        return str(complete_text(prompt) or "")
    raise RuntimeError("LLM provider does not support complete")


def _repair_json(llm: object, raw: str, error: Exception) -> str:
    repair_prompt = f"""The following quiz JSON was invalid.
Return corrected JSON only, preserving the original content as much as possible.
Validation or parse error: {type(error).__name__}: {str(error)[:600]}

Invalid content:
{raw[:20000]}
"""
    return _complete_json(llm, repair_prompt)


def _source_word_pack_lemmas(store: object, word_pack_ids: list[str]) -> tuple[list[str], list[QuizWordPackLink]]:
    lemmas: list[str] = []
    links: list[QuizWordPackLink] = []
    for word_pack_id in word_pack_ids:
        result = store.get_word_pack(word_pack_id)
        if result is None:
            links.append(
                QuizWordPackLink(
                    word_pack_id=word_pack_id,
                    lemma=word_pack_id,
                    status="skipped",
                    warning="WordPack が見つからなかったため、生成対象から除外しました。",
                )
            )
            continue
        lemma, _data, _created_at, _updated_at = result
        normalized = validate_lemma(lemma)
        lemmas.append(normalized)
        metadata = store.get_word_pack_metadata(word_pack_id)
        is_empty = False
        if isinstance(metadata, Mapping):
            counts = metadata.get("examples_category_counts") or {}
            if isinstance(counts, Mapping):
                is_empty = sum(int(v or 0) for v in counts.values()) == 0
        links.append(
            QuizWordPackLink(
                word_pack_id=word_pack_id,
                lemma=normalized,
                status="existing",
                is_empty=is_empty,
            )
        )
    return lemmas, links


def _dedupe_lemmas(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for group in groups:
        for raw in group:
            lemma = validate_lemma(raw)
            key = lemma.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(lemma)
    return out


def _find_occurrences(text: str, lemma: str, passage_id: str) -> list[QuizWordPackOccurrence]:
    occurrences: list[QuizWordPackOccurrence] = []
    escaped = re.escape(lemma)
    pattern = re.compile(rf"(?<![A-Za-z0-9'-]){escaped}(?![A-Za-z0-9'-])", re.IGNORECASE)
    for match in pattern.finditer(text):
        occurrences.append(
            QuizWordPackOccurrence(
                passage_id=passage_id,
                start=match.start(),
                end=match.end(),
            )
        )
    return occurrences


def _missing_source_warning(lemma: str) -> str:
    return f"指定 lemma `{lemma}` が本文中に見つかりませんでした。自然さを優先して未使用になった可能性があります。"


def _link_word_packs(
    *,
    store: object,
    quiz_data: dict[str, Any],
    existing_links: list[QuizWordPackLink],
    source_lemmas: list[str],
) -> list[QuizWordPackLink]:
    related_raw = quiz_data.get("related_lemmas") or []
    explanation_lemmas: list[str] = []
    for section in quiz_data.get("sections") or []:
        for question in section.get("questions") or []:
            explanation = question.get("explanation") or {}
            explanation_lemmas.extend(str(v) for v in explanation.get("related_lemmas") or [])
    all_lemmas = _dedupe_lemmas(
        source_lemmas,
        [str(v) for v in related_raw],
        explanation_lemmas,
    )
    source_keys = {lemma.lower() for lemma in source_lemmas}
    link_by_lemma = {link.lemma.lower(): link for link in existing_links if link.status == "existing"}
    passages = quiz_data.get("passages") or []
    linked: list[QuizWordPackLink] = []
    for lemma in all_lemmas:
        key = lemma.lower()
        existing = link_by_lemma.get(key)
        if existing is None:
            word_pack_id = store.find_word_pack_id_by_lemma(lemma)
            status = "existing" if word_pack_id else "missing"
            existing = QuizWordPackLink(
                word_pack_id=word_pack_id,
                lemma=lemma,
                status=status,
                is_empty=False,
            )
        occurrences: list[QuizWordPackOccurrence] = []
        for passage in passages:
            passage_id = str(passage.get("id") or "")
            body_en = str(passage.get("body_en") or "")
            if passage_id and body_en:
                occurrences.extend(_find_occurrences(body_en, lemma, passage_id))
        warning = existing.warning
        if key in source_keys and not occurrences:
            warning = _missing_source_warning(lemma)
        linked.append(existing.model_copy(update={"occurrences": occurrences, "warning": warning}))
    for link in existing_links:
        if link.status == "skipped":
            linked.append(link)
    return linked


def _stable_missing_link_id(quiz_id: str, lemma: str) -> str:
    digest = hashlib.sha1(lemma.lower().encode("utf-8")).hexdigest()[:16]
    return f"{quiz_id}:lemma:{digest}"


class QuizGenerateFlow:
    def __init__(
        self,
        *,
        store: object,
        llm: object | None = None,
        owner_user_id: str | None = None,
    ) -> None:
        self._store = store
        self._llm = llm
        self._owner_user_id = owner_user_id

    def run(self, req: QuizGenerateRequest) -> Quiz:
        generation_started_at = _now_iso()
        started = time.perf_counter()
        logger.info(
            "quiz_generation_started",
            format_profile=req.format_profile.value,
            generation_domain=req.generation_domain.value,
            domain_intensity=req.domain_intensity.value,
            difficulty=req.difficulty.value,
            section_count=req.section_count,
            questions_per_section=req.questions_per_section,
        )
        source_word_pack_lemmas, initial_links = _source_word_pack_lemmas(
            self._store,
            req.word_pack_ids,
        )
        source_lemmas = _dedupe_lemmas(source_word_pack_lemmas, req.lemmas)
        prompt = build_quiz_generation_prompt(
            format_profile=req.format_profile,
            generation_domain=req.generation_domain,
            domain_intensity=req.domain_intensity,
            difficulty=req.difficulty,
            lemmas=source_lemmas,
            section_count=req.section_count,
            questions_per_section=req.questions_per_section,
            include_translation=req.include_translation,
            topic_seed=req.topic_seed,
            avoid_topics=req.avoid_topics,
        )
        llm = self._llm or get_llm_provider(
            model_override=get_override_value(req, "model"),
            reasoning_override=get_override_value(req, "reasoning"),
            text_override=get_override_value(req, "text"),
        )
        llm_info = build_llm_info(req)
        raw = _complete_json(llm, prompt)
        if not raw.strip():
            logger.warning("quiz_generation_failed", reason_code="QUIZ_LLM_EMPTY")
            raise RuntimeError("QUIZ_LLM_EMPTY")
        try:
            data = parse_json_response(raw, prefer_json_object=True)
        except Exception as exc:
            repaired = _repair_json(llm, raw, exc)
            try:
                data = parse_json_response(repaired, prefer_json_object=True)
            except Exception as repair_exc:
                logger.warning("quiz_generation_failed", reason_code="QUIZ_JSON_PARSE_FAILED")
                raise RuntimeError("QUIZ_JSON_PARSE_FAILED") from repair_exc
        if not isinstance(data, dict):
            logger.warning("quiz_generation_failed", reason_code="QUIZ_SCHEMA_INVALID")
            raise RuntimeError("QUIZ_SCHEMA_INVALID")

        quiz_id = generate_quiz_id()
        generation_completed_at = _now_iso()
        duration_ms = int((time.perf_counter() - started) * 1000)
        linked = _link_word_packs(
            store=self._store,
            quiz_data=data,
            existing_links=initial_links,
            source_lemmas=source_lemmas,
        )
        payload = {
            **data,
            "id": quiz_id,
            "format_profile": req.format_profile.value,
            "generation_domain": req.generation_domain.value,
            "domain_intensity": req.domain_intensity.value,
            "difficulty": req.difficulty.value,
            "related_word_packs": [link.model_dump() for link in linked],
            "source_word_pack_ids": req.word_pack_ids,
            "source_lemmas": source_lemmas,
            "topic_seed": req.topic_seed,
            "avoid_topics": req.avoid_topics,
            "llm_model": llm_info.get("model"),
            "llm_params": str(llm_info.get("params")) if llm_info.get("params") else None,
            "generation_started_at": generation_started_at,
            "generation_completed_at": generation_completed_at,
            "generation_duration_ms": duration_ms,
            "guest_public": False,
            "owner_user_id": self._owner_user_id,
            "created_at": generation_completed_at,
            "updated_at": generation_completed_at,
        }
        try:
            quiz = Quiz.model_validate(payload)
        except Exception as exc:
            logger.warning("quiz_schema_invalid", reason_code="QUIZ_SCHEMA_INVALID", error=str(exc)[:1000])
            raise RuntimeError("QUIZ_SCHEMA_INVALID") from exc
        self._store.save_quiz(
            quiz.id,
            quiz.model_dump(mode="json"),
            [link.model_dump(mode="json") for link in quiz.related_word_packs],
        )
        saved = self._store.get_quiz(quiz.id)
        if saved is None:
            return quiz
        hydrated = Quiz.model_validate(saved)
        logger.info(
            "quiz_generation_saved",
            quiz_id=hydrated.id,
            question_count=sum(len(section.questions) for section in hydrated.sections),
            passage_count=len(hydrated.passages),
        )
        return hydrated


__all__ = ["QuizGenerateFlow", "generate_quiz_id", "_stable_missing_link_id"]
