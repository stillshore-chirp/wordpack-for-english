"""カテゴリ別の例文生成フロー。backend.providers の分割構成に対応。"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import HTTPException

from ..flows.article_import import ArticleImportFlow
from ..flows.word_pack import WordPackFlow
from ..id_factory import generate_word_pack_id
from ..logging import logger
from ..models.article import ArticleImportRequest
from ..models.word import ExampleCategory, WordPack
from ..observability import span
from ..providers import get_llm_provider
from ..sense_title import choose_sense_title
from ..store import store as _default_store
from ..store.proxy import CurrentStoreProxy

store = CurrentStoreProxy(_default_store)


class CategoryGenerateAndImportFlow:
    """Orchestrates: generate one lemma for a category -> ensure empty WordPack ->
    generate 2 examples for the category -> import each example as an article.

    - Avoids duplicates by checking existing WordPack by lemma; retries up to 3 times.
    - Uses existing flows for examples and article import to keep contracts consistent.
    """

    def __init__(
        self,
        *,
        model: Optional[str] = None,
        reasoning: Optional[dict] = None,
        text: Optional[dict] = None,
        owner_user_id: str | None = None,
    ) -> None:
        self._llm = get_llm_provider(
            model_override=model,
            reasoning_override=reasoning,
            text_override=text,
        )
        # 新しい backend.providers パッケージで作成した LLM を保持する。
        # 呼び出し元から渡された LLM パラメータを保持し、下流の ArticleImportFlow へも同一の契約で引き継ぐ
        self._llm_info = {
            "model": model,
            "params": None,
        }
        self._overrides = {
            "model": model,
            "reasoning": reasoning,
            # ArticleImportFlow は text_opts というキー名を採用しているため、ここで変換
            "text_opts": text,
        }
        self._owner_user_id = owner_user_id

    def _prompt_lemma(
        self, category: ExampleCategory, attempted: list[str], avoid_existing: list[str]
    ) -> str:
        attempted_list = ", ".join(attempted) if attempted else "(none)"
        existing_list = ", ".join(avoid_existing[:30]) if avoid_existing else "(none)"
        return (
            "あなたは例文生成のためにカテゴリに密接に関連する英語の lemma を選定する。\n"
            f"対象カテゴリ: {category.value}。\n"
            '出力は {"lemma": "..."} というキーを1つだけ持つ JSON オブジェクト1件に限定し、説明文を書かないこと。\n'
            "指示:\n"
            "- lemma は対象カテゴリ（Dev, CS, LLM, Business, Common）の専門領域に強く関連させる。\n"
            "- 試行ごとに主流語とニッチな専門語をバランスよく含め、繰り返しの偏りを避ける。\n"
            "- 単語1語が望ましいが、一般的な連語やドメイン用語であれば複数語表現も許容する。\n"
            "- 長さは1〜64文字。ASCIIの英字・ハイフン・アポストロフィ・空白のみを使用する。\n"
            "- 極端に一般的な機能語や取るに足らない語は避ける。\n"
            "- 既に試行済みまたは既存の lemma を出力しないこと。\n"
            "  本セッションで試行済み: " + attempted_list + "\n"
            "  データベースに存在する語（一部）: " + existing_list + "\n"
            "出力は必ず JSON のみ。"
        )

    def _existing_lemmas_sample(self, limit: int = 50) -> list[str]:
        try:
            items = store.list_word_packs(limit=limit, offset=0)
        except Exception:
            return []
        out: list[str] = []
        for _id, lemma, _sense_title, _c, _u in items:
            try:
                out.append(str(lemma).strip().lower())
            except Exception:
                continue
        # unique preserving order
        seen: set[str] = set()
        uniq: list[str] = []
        for w in out:
            if w and w not in seen:
                seen.add(w)
                uniq.append(w)
        return uniq

    def _fallback_candidates(self, category: ExampleCategory) -> list[str]:
        base: list[str] = [
            # generic, but not function words; safe ascii
            "memoization",
            "serialization",
            "throughput",
            "latency",
            "idempotency",
            "refactor",
            "concurrency",
            "race condition",
            "transaction",
            "consistency",
            "sharding",
            "load testing",
            "rate limiting",
            "retry policy",
            "circuit breaker",
        ]
        by_cat: dict[str, list[str]] = {
            "Dev": base + ["feature flag", "observability", "telemetry"],
            "CS": base + ["graph traversal", "hash table", "binary search"],
            "LLM": base + ["tokenization", "prompt engineering", "hallucination"],
            "Business": base + ["stakeholder", "arbitrage", "churn"],
            "Common": base + ["resilience", "trade-off", "estimate"],
        }
        return by_cat.get(category.value, base)

    def _choose_new_lemma(self, category: ExampleCategory, max_retries: int = 5) -> str:
        attempted: list[str] = []
        avoid_existing = self._existing_lemmas_sample(limit=60)
        for _ in range(max_retries):
            prompt = self._prompt_lemma(category, attempted, avoid_existing)
            # 観測: プロンプトと LLM 呼び出し
            try:
                with span(
                    trace=None,
                    name="category.pick_lemma.prompt",
                    input={
                        "prompt_chars": len(prompt),
                        "category": category.value,
                        "attempted": len(attempted),
                    },
                ):
                    pass
            except Exception:
                pass
            with span(
                trace=None,
                name="category.pick_lemma.llm",
                input={"prompt_chars": len(prompt)},
            ):
                out = self._llm.complete(prompt)
            try:
                data = json.loads((out or "").strip().strip("`"))
                lemma_raw = str(data.get("lemma") or "").strip()
            except Exception:
                lemma_raw = ""
            lemma = lemma_raw.lower()
            # basic normalization
            if not lemma or len(lemma) > 64:
                attempted.append(lemma_raw or "")
                continue
            if not all((ch.isalpha() or ch in {"-", "'", " "}) for ch in lemma):
                attempted.append(lemma)
                continue
            # reject duplicates
            if store.find_word_pack_id_by_lemma(lemma) is not None:
                attempted.append(lemma)
                continue
            logger.info("category_pick_lemma", category=category.value, lemma=lemma)
            return lemma
        # Fallback: choose from a deterministic candidate list filtered by existing
        candidates = self._fallback_candidates(category)
        for cand in candidates:
            lc = str(cand).strip().lower()
            if not lc or lc in attempted:
                continue
            if store.find_word_pack_id_by_lemma(lc) is None:
                logger.info(
                    "category_pick_lemma_fallback", category=category.value, lemma=lc
                )
                return lc
        # still no choice
        raise HTTPException(
            status_code=409,
            detail={
                "message": "No unique lemma could be chosen after retries",
                "reason_code": "LEMMA_DUPLICATE_OR_INVALID",
                "attempted": attempted,
            },
        )

    def _ensure_empty_wordpack(self, lemma: str) -> str:
        with span(
            trace=None, name="category.ensure_wordpack.lookup", input={"lemma": lemma}
        ):
            existing = store.find_word_pack_id_by_lemma(lemma)
        if existing is not None:
            return existing
        empty_word_pack = WordPack(
            lemma=lemma,
            sense_title=choose_sense_title(None, [], lemma=lemma, limit=20),
            pronunciation={
                "ipa_GA": None,
                "ipa_RP": None,
                "syllables": None,
                "stress_index": None,
                "linking_notes": [],
            },
            senses=[],
            collocations={
                "general": {"verb_object": [], "adj_noun": [], "prep_noun": []},
                "academic": {"verb_object": [], "adj_noun": [], "prep_noun": []},
            },
            contrast=[],
            examples={"Dev": [], "CS": [], "LLM": [], "Business": [], "Common": []},
            etymology={"note": "-", "confidence": "low"},
            study_card="",
            citations=[],
            confidence="low",
        )
        wp_id = generate_word_pack_id()
        with span(
            trace=None, name="category.ensure_wordpack.create", input={"lemma": lemma}
        ):
            store.save_word_pack(
                wp_id,
                lemma,
                empty_word_pack.model_dump_json(),
                metadata={"owner_user_id": self._owner_user_id}
                if self._owner_user_id
                else None,
            )
        return wp_id

    def _generate_two_examples(
        self, lemma: str, category: ExampleCategory
    ) -> list[dict]:
        flow = WordPackFlow(chroma_client=None, llm=self._llm, llm_info=self._llm_info)
        plan = {category: 2}
        with span(
            trace=None,
            name="category.generate_examples",
            input={"lemma": lemma, "category": category.value, "count": 2},
        ):
            gen = flow.generate_examples_for_categories(lemma, plan)
        items_model = gen.get(category, [])
        items: list[dict] = []
        for it in items_model:
            items.append(
                {
                    "en": it.en,
                    "ja": it.ja,
                    "grammar_ja": it.grammar_ja,
                    "llm_model": it.llm_model,
                    "llm_params": it.llm_params,
                }
            )
        if len(items) < 2:
            raise HTTPException(
                status_code=502, detail="LLM returned insufficient examples"
            )
        return items[:2]

    def run(self, category: ExampleCategory) -> dict:
        lemma = self._choose_new_lemma(category)
        wp_id = self._ensure_empty_wordpack(lemma)
        items = self._generate_two_examples(lemma, category)
        with span(
            trace=None,
            name="category.save_examples",
            input={
                "word_pack_id": wp_id,
                "category": category.value,
                "count": len(items),
            },
        ):
            store.append_examples(wp_id, category.value, items)

        # Import each example as an article
        article_ids: list[str] = []
        failures: list[dict[str, Any]] = []
        art_flow = ArticleImportFlow(owner_user_id=self._owner_user_id)
        for idx, ex in enumerate(items):
            try:
                with span(
                    trace=None,
                    name="category.import_article",
                    input={
                        "lemma": lemma,
                        "category": category.value,
                        "text_chars": len(str(ex.get("en") or "")),
                    },
                ):
                    # ArticleImportFlow に LLM パラメータを引き継ぐ
                    req_payload = ArticleImportRequest(
                        text=str(ex.get("en") or ""),
                        model=self._overrides.get("model"),
                        reasoning=self._overrides.get("reasoning"),
                        text_opts=self._overrides.get("text_opts"),
                        generation_category=category,
                    )
                    res = art_flow.run(req_payload)
                article_ids.append(res.id)
            except Exception as exc:  # pragma: no cover - error path validated via tests
                error_class = exc.__class__.__name__
                logger.warning(
                    "category_example_import_failed",
                    lemma=lemma,
                    category=category.value,
                    example_index=idx,
                    error=str(exc),
                    error_class=error_class,
                )
                failures.append(
                    {
                        "example_index": idx,
                        "error": str(exc),
                        "error_class": error_class,
                    }
                )
        success_count = len(article_ids)
        failed_count = len(failures)
        total_examples = len(items)
        if success_count == 0 and total_examples > 0:
            logger.error(
                "category_generate_import_failed_all",
                lemma=lemma,
                category=category.value,
                generated_examples=total_examples,
                failed_examples=failed_count,
            )
            detail: dict[str, Any] = {
                "message": "Failed to import every generated example as an article",
                "reason_code": "CATEGORY_IMPORT_FAILED_ALL",
                "generated_examples": total_examples,
                "failed_examples": failed_count,
            }
            if failures:
                detail["failures"] = failures[:3]
            raise HTTPException(status_code=502, detail=detail)
        if failed_count:
            logger.warning(
                "category_generate_import_partial_success",
                lemma=lemma,
                category=category.value,
                generated_examples=total_examples,
                imported_articles=success_count,
                failed_examples=failed_count,
            )
        response: dict[str, Any] = {
            "lemma": lemma,
            "word_pack_id": wp_id,
            "category": category.value,
            "generated_examples": total_examples,
            "article_ids": article_ids,
        }
        if failed_count:
            response["failed_examples"] = failed_count
        return response
