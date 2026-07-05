from __future__ import annotations
"""記事インポート Flow。backend.providers の分割後 API を利用する。"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Optional, TypedDict

from fastapi import HTTPException

from ..config import settings
from ..domain.article.lemma_filter import STOP_LEMMAS, filter_article_lemmas
from ..flows.word_pack import WordPackFlow
from ..id_factory import generate_word_pack_id
from ..infrastructure.llm.json_response_parser import parse_json_response, strip_code_fences
from ..logging import logger
from ..models.article import (
    ArticleDetailResponse,
    ArticleImportRequest,
    ArticleWordPackLink,
)
from ..models.word import WordPack
from ..observability import span
from ..providers import get_llm_provider
from ..sense_title import choose_sense_title
from ..store import store as _default_store
from ..store.proxy import CurrentStoreProxy
from . import StateGraph, create_state_graph

store = CurrentStoreProxy(_default_store)


class _ArticleState(TypedDict, total=False):
    original_text: str
    # 以下は段階的生成の出力を保持する
    lemmas: list[str]
    links: list[ArticleWordPackLink]
    article_id: str
    title_en: str
    body_en: str
    body_ja: str
    notes_ja: Optional[str]
    llm_model: Optional[str]
    llm_params: Optional[str]
    generation_category: Optional[str]
    generation_started_at: Optional[str]
    generation_completed_at: Optional[str]
    created_at: str
    updated_at: str


class ArticleImportFlow:
    """Article import AI flow orchestrated with LangGraph.

    入力テキストからタイトル/訳/注釈/lemmas をLLMで抽出し、
    lemmas を WordPack に連携（既存確認/未存在なら空パック作成）した上で
    記事データとして保存する。
    """

    _STOP_LEMMAS: set[str] = STOP_LEMMAS

    _BASIC_LEMMAS: set[str] = {
        "about",
        "above",
        "across",
        "action",
        "actually",
        "after",
        "again",
        "against",
        "age",
        "ago",
        "air",
        "all",
        "almost",
        "alone",
        "along",
        "already",
        "always",
        "american",
        "among",
        "another",
        "answer",
        "any",
        "anyone",
        "anything",
        "area",
        "around",
        "ask",
        "away",
        "back",
        "bad",
        "base",
        "because",
        "become",
        "before",
        "begin",
        "behind",
        "believe",
        "best",
        "better",
        "big",
        "black",
        "body",
        "book",
        "both",
        "business",
        "call",
        "called",
        "car",
        "care",
        "case",
        "center",
        "change",
        "child",
        "children",
        "city",
        "class",
        "clear",
        "close",
        "cold",
        "college",
        "come",
        "common",
        "company",
        "country",
        "course",
        "create",
        "day",
        "days",
        "development",
        "different",
        "difficult",
        "direction",
        "door",
        "down",
        "early",
        "education",
        "enough",
        "even",
        "evening",
        "event",
        "ever",
        "every",
        "everyone",
        "everything",
        "example",
        "experience",
        "family",
        "far",
        "father",
        "feel",
        "felt",
        "few",
        "find",
        "first",
        "follow",
        "food",
        "form",
        "friend",
        "friends",
        "front",
        "full",
        "game",
        "general",
        "get",
        "girl",
        "give",
        "given",
        "good",
        "government",
        "great",
        "group",
        "hand",
        "hands",
        "happen",
        "happened",
        "hard",
        "head",
        "health",
        "hear",
        "heard",
        "help",
        "high",
        "history",
        "home",
        "house",
        "idea",
        "important",
        "interest",
        "interesting",
        "issue",
        "job",
        "keep",
        "kind",
        "know",
        "known",
        "large",
        "last",
        "later",
        "learn",
        "least",
        "leave",
        "left",
        "letter",
        "life",
        "like",
        "line",
        "little",
        "local",
        "long",
        "look",
        "lot",
        "love",
        "main",
        "major",
        "make",
        "making",
        "man",
        "many",
        "matter",
        "mean",
        "member",
        "men",
        "might",
        "million",
        "money",
        "month",
        "months",
        "morning",
        "most",
        "mother",
        "move",
        "much",
        "music",
        "name",
        "national",
        "need",
        "never",
        "new",
        "next",
        "night",
        "nothing",
        "number",
        "often",
        "old",
        "once",
        "open",
        "order",
        "other",
        "others",
        "part",
        "people",
        "perhaps",
        "place",
        "plan",
        "play",
        "point",
        "power",
        "present",
        "president",
        "problem",
        "public",
        "question",
        "quite",
        "real",
        "really",
        "reason",
        "receive",
        "research",
        "right",
        "room",
        "run",
        "school",
        "set",
        "several",
        "show",
        "small",
        "someone",
        "something",
        "sometimes",
        "start",
        "state",
        "story",
        "student",
        "study",
        "such",
        "system",
        "take",
        "team",
        "tell",
        "term",
        "thing",
        "think",
        "thought",
        "though",
        "together",
        "today",
        "told",
        "toward",
        "town",
        "try",
        "turn",
        "understand",
        "university",
        "use",
        "used",
        "using",
        "very",
        "want",
        "war",
        "water",
        "week",
        "weeks",
        "while",
        "white",
        "whole",
        "why",
        "woman",
        "women",
        "word",
        "work",
        "world",
        "write",
        "year",
        "years",
        "young",
        # 典型的な挨拶・日常語
        "hello",
        "hi",
        "thanks",
        "thank",
        "please",
        "okay",
        "ok",
        "bye",
        "welcome",
        "sorry",
        "yeah",
        "yep",
        # 曜日・月
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    }

    def __init__(self, *, owner_user_id: str | None = None) -> None:
        self._owner_user_id = owner_user_id

    # ---- 役割別プロンプト（サブグラフ相当） ----
    def _prompt_title(self, text: str) -> str:
        return (
            """入力テキストの内容を忠実に反映した、10語以内の非常に短い英語タイトルを作成する。
制約:
- 簡潔なタイトルに必要な範囲を超えて言い換えない。
- 引用符などを付けず、タイトル本文のみを出力する。
入力:
<INPUT_START>\n"""
            + text
            + """\n<INPUT_END>"""
        )

    def _prompt_translation(self, text: str) -> str:
        return (
            """入力された英語テキストを日本語へ忠実に翻訳する。
制約:
- 要約や言い換えを行わない。
- 意味を完全かつ正確に保持する。
出力は翻訳された日本語本文のみ（追加の解説は禁止）。
入力:
<INPUT_START>\n"""
            + text
            + """\n<INPUT_END>"""
        )

    def _prompt_explanation(self, text: str) -> str:
        return (
            """入力された英語テキストについて、日本語で 2〜4 文の詳細な解説を書く。
文法分析を最優先し、主要な文構造や時制・相・態の選択理由を明示する。
慣用表現・句動詞・コロケーション・定型表現があれば、そのニュアンスと使用制約を説明する。
専門用語が登場する場合は、文中でどのように機能しているかを簡潔に示す。
大学教育を受けた学習者向けに、指導的で具体的な解説にする。
出力は解説文のみとし、引用符などは付けない。
入力:
<INPUT_START>\n"""
            + text
            + """\n<INPUT_END>"""
        )

    def _prompt_lemmas(self, text: str) -> str:
        return (
            """入力英語テキストから、学習価値の高い lemma と複数語表現のみを抽出して列挙する。
厳格フィルタ: 機能語（冠詞・助動詞・be 動詞・単純な代名詞・基本的な前置詞/接続詞）や、I, am, a, the, be, is, are, to, of, and, in, on, for, with, at, by, from, as といった些末語を除外する。
CEFR A1〜A2 の日常語（挨拶・カレンダー/時間語・基本動詞 get/go/make/take など）も除外する。
大学生以上向けの語彙（CEFR B2+）を中心に、洗練された一般学術語（例: resilience, articulate）と専門・技術用語を含める。
高度な用法を示す複数語表現（句動詞・イディオム・コロケーション）も取り入れる。
同じ語が一般語と専門語で並んで現れた場合は、より精密で希少な語を優先しつつ、信頼できる学術語であれば広く使われていても除外しない。
目安は 5〜30 件。
返却形式: 文字列の JSON 配列。例: ["supply chain", "mitigate", "trade-off"]。
入力:
<INPUT_START>\n"""
            + text
            + """\n<INPUT_END>"""
        )

    def _strip_code_fences(self, text: str) -> str:
        """Remove surrounding Markdown code fences like ```json ... ``` if present.

        入力文字列の前後に存在する Markdown のコードフェンスを取り除く。
        """
        return strip_code_fences(text, prefer_json_object=False)

    def _complete_text(self, llm: object, prompt: str) -> str:
        """プレーンテキスト生成では Responses API の JSON mode を使わない。"""

        complete_text = getattr(llm, "complete_text", None)
        if callable(complete_text):
            return str(complete_text(prompt) or "")
        complete = getattr(llm, "complete")
        return str(complete(prompt) or "")

    def _post_filter_lemmas(self, raw: list[str]) -> list[str]:
        return filter_article_lemmas(raw, basic_lemmas=self._BASIC_LEMMAS)

    def _link_or_create_wordpacks_state(
        self, lemmas: list[str]
    ) -> tuple[list[ArticleWordPackLink], list[str]]:
        """WordPack 紐付けとフォールバックの実装本体。

        新規メンバーでも追えるように、検索（既存確認）→プレースホルダー作成→
        is_empty 推定の順で記述する。Firestore 障害時でも例外を外へ漏らさず、
        構造化ログとユーザー向け警告メッセージを返す。
        """

        links: list[ArticleWordPackLink] = []
        warnings: list[str] = []

        for lemma in lemmas:
            normalized = str(lemma or "").strip()
            if not normalized:
                continue

            warning_msg: str | None = None
            lookup_error = False
            try:
                lookup_result = store.find_word_pack_id_by_lemma(
                    normalized, diagnostics=True
                )
                if isinstance(lookup_result, tuple):
                    wp_id, lookup_error = lookup_result
                else:
                    wp_id = lookup_result
            except Exception as exc:  # pragma: no cover - defensive guard
                lookup_error = True
                wp_id = None
                warning_msg = (
                    f"{normalized}: 既存の WordPack 検索に失敗したためプレースホルダー"
                    "を作成しました。ネットワーク復旧後に再確認してください。"
                )
                logger.warning(
                    "article_link_wordpack_lookup_failed",
                    lemma=normalized,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                )

            status = "existing"
            if wp_id is None:
                empty_word_pack = WordPack(
                    lemma=normalized,
                    sense_title=choose_sense_title(None, [], lemma=normalized, limit=20),
                    pronunciation={
                        "ipa_GA": None,
                        "ipa_RP": None,
                        "syllables": None,
                        "stress_index": None,
                        "linking_notes": [],
                    },
                    senses=[],
                    collocations={
                        "general": {
                            "verb_object": [],
                            "adj_noun": [],
                            "prep_noun": [],
                        },
                        "academic": {
                            "verb_object": [],
                            "adj_noun": [],
                            "prep_noun": [],
                        },
                    },
                    contrast=[],
                    examples={
                        "Dev": [],
                        "CS": [],
                        "LLM": [],
                        "Business": [],
                        "Common": [],
                    },
                    etymology={"note": "-", "confidence": "low"},
                    study_card="",
                    citations=[],
                    confidence="low",
                )
                wp_id = generate_word_pack_id()

                try:
                    store.save_word_pack(
                        wp_id,
                        normalized,
                        empty_word_pack.model_dump_json(),
                        metadata={"owner_user_id": self._owner_user_id}
                        if self._owner_user_id
                        else None,
                    )
                    status = "created"
                    if lookup_error and warning_msg is None:
                        warning_msg = (
                            f"{normalized}: Firestore 検索が不安定だったため、"
                            "プレースホルダーを生成しました。内容を後で補完してください。"
                        )
                except Exception as exc:
                    warning_msg = (
                        f"{normalized}: WordPack を作成できなかったためリンクをスキップ"
                        "しました。再実行または手動登録を検討してください。"
                    )
                    logger.error(
                        "article_link_wordpack_save_failed",
                        lemma=normalized,
                        error=str(exc),
                        error_class=exc.__class__.__name__,
                    )
                    warnings.append(warning_msg)
                    continue

            is_empty = True
            try:
                result = store.get_word_pack(wp_id)
                if result is not None:
                    _, data_json, _, _ = result
                    d = json.loads(data_json)
                    senses_empty = not d.get("senses")
                    ex = d.get("examples") or {}
                    examples_empty = all(
                        not (ex.get(k) or [])
                        for k in ["Dev", "CS", "LLM", "Business", "Common"]
                    )
                    study_empty = not bool((d.get("study_card") or "").strip())
                    is_empty = bool(senses_empty and examples_empty and study_empty)
            except Exception:
                is_empty = True

            links.append(
                ArticleWordPackLink(
                    word_pack_id=wp_id,
                    lemma=normalized,
                    status=status,
                    is_empty=is_empty,
                    warning=warning_msg,
                )
            )
            if warning_msg:
                warnings.append(warning_msg)

        return links, warnings

    def run(self, req: ArticleImportRequest) -> ArticleDetailResponse:
        if not req.text or not req.text.strip():
            logger.info("article_import_empty_text")
            raise HTTPException(status_code=400, detail="text is required")

        llm = get_llm_provider(
            model_override=getattr(req, "model", None),
            reasoning_override=getattr(req, "reasoning", None),
            text_override=getattr(req, "text_opts", None),
        )
        # backend.providers パッケージから取得した LLM を Flow 内で共有する。

        # UI/契約と整合する LLM パラメータ表示用の簡易連結
        def _fmt_llm_params() -> str | None:
            parts: list[str] = []
            try:
                r = getattr(req, "reasoning", None) or {}
                if isinstance(r, dict) and r.get("effort"):
                    parts.append(f"reasoning.effort={r.get('effort')}")
                t = getattr(req, "text_opts", None) or {}
                if isinstance(t, dict) and t.get("verbosity"):
                    parts.append(f"text.verbosity={t.get('verbosity')}")
            except Exception:
                pass
            return ";".join(parts) if parts else None

        original_text = req.text.strip()
        selected_llm_model = getattr(req, "model", None) or settings.llm_model
        formatted_llm_params = _fmt_llm_params()
        generation_category = None
        try:
            cat = getattr(req, "generation_category", None)
            if cat:
                generation_category = getattr(cat, "value", None) or str(cat)
        except Exception:
            generation_category = None
        # datetime.utcnow() は Python 3.12 で非推奨となったため、UTC タイムゾーンを明示
        # 指定して aware datetime を記録する。これにより API 利用者がタイムゾーンを
        # 推測する必要がなくなり、DeprecationWarning も解消される。
        generation_started_at = datetime.now(UTC).isoformat()

        try:
            graph = create_state_graph()
            # 初期 state（段階出力を段階的に埋めていく）
            state: _ArticleState = {
                "original_text": original_text,
                "lemmas": [],
                "links": [],
                "title_en": "",
                "body_en": original_text,
                "body_ja": "",
                "notes_ja": None,
                "llm_model": selected_llm_model,
                "llm_params": formatted_llm_params,
                "generation_category": generation_category,
                "generation_started_at": generation_started_at,
            }
            # 保存済みIDを閉包で保持（LangGraphの差分返却による欠落対策）
            saved_article_id: Optional[str] = None
            # 入力の要点を構造化ログ
            import hashlib as _hf  # local import

            preview = original_text[:120]
            payload = {
                "text_chars": len(original_text),
                "text_preview": preview,
            }
            if original_text:
                try:
                    payload["text_sha256"] = _hf.sha256(
                        original_text.encode("utf-8", errors="ignore")
                    ).hexdigest()
                except Exception:
                    pass
            logger.info("article_import_start", **payload)

            # ---- 役割別 生成ノード ----
            def _generate_title(s: _ArticleState) -> _ArticleState:
                # LangGraph の最小スキーマで state から "original_text" が脱落する場合があるため、
                # クロージャの original_text を直接参照する。
                txt = original_text
                pr = self._prompt_title(txt)
                payload = {"prompt_chars": len(pr), "prompt_preview": pr[:200]}
                with span(trace=None, name="article.title.prompt", input=payload):
                    pass
                with span(
                    trace=None,
                    name="article.title.llm",
                    input={"prompt_chars": len(pr)},
                ):
                    out = self._complete_text(llm, pr)
                t = str(out or "").strip()
                t = self._strip_code_fences(t)
                # 安全側: 空なら Untitled（UI互換）。ダミー生成ではなく保存時に明示化するだけ。
                s["title_en"] = t or "Untitled"
                logger.info(
                    "article_import_title_generated", title_len=len(s["title_en"])
                )
                return s

            def _generate_translation(s: _ArticleState) -> _ArticleState:
                txt = original_text
                pr = self._prompt_translation(txt)
                with span(
                    trace=None,
                    name="article.translation.prompt",
                    input={"prompt_chars": len(pr)},
                ):
                    pass
                with span(
                    trace=None,
                    name="article.translation.llm",
                    input={"prompt_chars": len(pr)},
                ):
                    out = self._complete_text(llm, pr)
                ja = str(out or "").strip()
                ja = self._strip_code_fences(ja)
                s["body_ja"] = ja
                logger.info(
                    "article_import_translation_generated", body_ja_chars=len(ja)
                )
                return s

            def _generate_explanation(s: _ArticleState) -> _ArticleState:
                txt = original_text
                pr = self._prompt_explanation(txt)
                with span(
                    trace=None,
                    name="article.explanation.prompt",
                    input={"prompt_chars": len(pr)},
                ):
                    pass
                with span(
                    trace=None,
                    name="article.explanation.llm",
                    input={"prompt_chars": len(pr)},
                ):
                    out = self._complete_text(llm, pr)
                note = str(out or "").strip()
                note = self._strip_code_fences(note)
                s["notes_ja"] = note or None
                logger.info(
                    "article_import_explanation_generated",
                    notes_ja_chars=len(note or ""),
                )
                return s

            def _parse_lemmas_json(raw: str) -> list[str]:
                try:
                    data = parse_json_response(str(raw), prefer_json_object=False)
                    if isinstance(data, list):
                        return [str(x) for x in data]
                    if isinstance(data, dict) and isinstance(data.get("lemmas"), list):
                        return [str(x) for x in data.get("lemmas", [])]
                except Exception as exc:
                    logger.info(
                        "article_import_lemmas_json_parse_failed", error=str(exc)
                    )
                return []

            def _generate_lemmas(s: _ArticleState) -> _ArticleState:
                txt = original_text
                pr = self._prompt_lemmas(txt)
                with span(
                    trace=None,
                    name="article.lemmas.prompt",
                    input={"prompt_chars": len(pr)},
                ):
                    pass
                with span(
                    trace=None,
                    name="article.lemmas.llm",
                    input={"prompt_chars": len(pr)},
                ):
                    out = llm.complete(pr)
                raw_list = _parse_lemmas_json(str(out or ""))
                s["lemmas"] = raw_list
                logger.info("article_import_lemmas_generated", count=len(raw_list))
                return s

            def _filter_lemmas(s: _ArticleState) -> _ArticleState:
                with span(trace=None, name="article.filter_lemmas"):
                    try:
                        raw_list = [str(x) for x in (s.get("lemmas") or [])]
                        lemmas = self._post_filter_lemmas(raw_list)
                    except Exception:
                        lemmas = []
                s["lemmas"] = lemmas
                logger.info(
                    "article_import_lemmas_filtered",
                    input_count=len((raw_list if "raw_list" in locals() else [])),
                    output_count=len(lemmas),
                )
                return s

            def _link_or_create_wordpacks(s: _ArticleState) -> _ArticleState:
                lemmas = s.get("lemmas", [])
                with span(
                    trace=None,
                    name="article.link_or_create_wordpacks",
                    input={"lemma_count": len(lemmas)},
                ):
                    links, warnings = self._link_or_create_wordpacks_state(lemmas)
                s["links"] = links
                if warnings:
                    existing = list(s.get("warnings", []))
                    s["warnings"] = [*existing, *warnings]
                created = sum(1 for l in links if l.status == "created")
                logger.info(
                    "article_import_link_or_create_done",
                    total=len(links),
                    created=created,
                    existing=len(links) - created,
                    warnings=len(warnings),
                )
                return s

            def _save_article(s: _ArticleState) -> _ArticleState:
                title_en = str(s.get("title_en") or "Untitled").strip() or "Untitled"
                body_en = original_text  # 英語原文はそのまま
                body_ja = str(s.get("body_ja") or "").strip()
                notes_ja = str(s.get("notes_ja") or "").strip() or None
                # LangGraph の差分返却で state からキーが脱落しても閉包の選択値で補完する
                llm_model = (
                    str((s.get("llm_model") or selected_llm_model or "")).strip()
                    or None
                )
                llm_params = (
                    str((s.get("llm_params") or formatted_llm_params or "")).strip()
                    or None
                )
                generation_category_local = (
                    str(
                        (s.get("generation_category") or generation_category or "")
                    ).strip()
                    or None
                )
                started_at = (
                    str(
                        (s.get("generation_started_at") or generation_started_at or "")
                    ).strip()
                    or None
                )
                # 完了時刻も同様に UTC aware で保存し、計測の一貫性を維持する。
                completed_at = datetime.now(UTC).isoformat()
                s["generation_completed_at"] = completed_at
                duration_ms = None
                try:
                    if started_at:
                        start_dt = datetime.fromisoformat(started_at)
                        end_dt = datetime.fromisoformat(completed_at)
                        # 端数切り上げで 1ms 以上に丸める（実測が0を下回らないようガード）
                        raw_ms = (end_dt - start_dt).total_seconds() * 1000.0
                        if raw_ms <= 0:
                            duration_ms = 0
                        else:
                            import math as _m

                            duration_ms = max(1, int(_m.ceil(raw_ms)))
                except Exception:
                    duration_ms = None
                if duration_ms is not None:
                    s["generation_duration_ms"] = duration_ms

                with span(trace=None, name="article.save_article"):
                    article_id = f"art:{uuid.uuid4().hex[:12]}"
                    # 閉包へも確実に退避
                    nonlocal saved_article_id
                    saved_article_id = article_id
                    store.save_article(
                        article_id,
                        title_en=title_en,
                        body_en=body_en,
                        body_ja=body_ja,
                        notes_ja=notes_ja,
                        llm_model=llm_model,
                        llm_params=llm_params,
                        generation_category=generation_category_local,
                        related_word_packs=[
                            (l.word_pack_id, l.lemma, l.status)
                            for l in s.get("links", [])
                        ],
                        created_at=started_at,
                        updated_at=completed_at,
                        generation_started_at=started_at,
                        generation_completed_at=completed_at,
                        generation_duration_ms=duration_ms,
                        owner_user_id=self._owner_user_id,
                    )
                    meta = store.get_article(article_id)
                    created_at = ""
                    updated_at = ""
                    started_at_db = started_at
                    completed_at_db = completed_at
                    duration_ms_db = duration_ms
                    if meta:
                        created_at = str(meta[7] or "")
                        updated_at = str(meta[8] or "")
                        # DB の値が空なら閉包/既定値をフォールバック
                        started_at_db = (
                            (str(meta[9] or "").strip() or None)
                            or started_at
                            or created_at
                            or generation_started_at
                        )
                        completed_at_db = (
                            (str(meta[10] or "").strip() or None)
                            or completed_at
                            or updated_at
                        )
                        if len(meta) >= 12:
                            duration_ms_db = (
                                meta[11] if meta[11] is not None else duration_ms_db
                            )
                        s["generation_category"] = meta[6] or generation_category_local
                        # LLM メタも欠落時にフォールバック（UI の未記録を避ける）
                        try:
                            if not (meta[4] or None):
                                s["llm_model"] = llm_model
                            else:
                                s["llm_model"] = meta[4]
                            if not (meta[5] or None):
                                s["llm_params"] = llm_params
                            else:
                                s["llm_params"] = meta[5]
                        except Exception:
                            pass
                    if started_at_db:
                        s["generation_started_at"] = started_at_db
                    if completed_at_db:
                        s["generation_completed_at"] = completed_at_db
                    if duration_ms_db is not None:
                        s["generation_duration_ms"] = duration_ms_db
                    created_at = created_at or (started_at_db or "")
                    updated_at = updated_at or (completed_at_db or "")

                    # --- Post-save repair: fill missing LLM meta and duration ---
                    try:
                        needs_resave = False
                        # 1) duration: if 0/None but timestamps exist, recompute with ceil to >=1ms
                        fixed_duration: int | None = duration_ms_db
                        if (
                            (fixed_duration is None or fixed_duration == 0)
                            and started_at_db
                            and completed_at_db
                        ):
                            try:
                                _st = datetime.fromisoformat(started_at_db)
                                _ed = datetime.fromisoformat(completed_at_db)
                                raw = (_ed - _st).total_seconds() * 1000.0
                                if raw > 0:
                                    import math as _m2

                                    fixed_duration = max(1, int(_m2.ceil(raw)))
                                else:
                                    fixed_duration = 0
                            except Exception:
                                fixed_duration = duration_ms_db
                        # 2) LLM meta: ensure model/params not empty
                        fixed_model = str((s.get("llm_model") or "").strip() or "")
                        fixed_params = str((s.get("llm_params") or "").strip() or "")
                        if not fixed_model:
                            fixed_model = str(llm_model or "")
                        if not fixed_params:
                            fixed_params = str(llm_params or "")
                        # Decide resave
                        if (duration_ms_db is None or duration_ms_db == 0) and (
                            fixed_duration is not None and fixed_duration > 0
                        ):
                            needs_resave = True
                        if (not (meta and meta[4])) and fixed_model:
                            needs_resave = True
                        if (not (meta and meta[5])) and fixed_params:
                            needs_resave = True
                        if needs_resave:
                            store.save_article(
                                article_id,
                                title_en=title_en,
                                body_en=body_en,
                                body_ja=body_ja,
                                notes_ja=notes_ja,
                                llm_model=(fixed_model or None),
                                llm_params=(fixed_params or None),
                                generation_category=s.get("generation_category")
                                or generation_category_local,
                                related_word_packs=[
                                    (l.word_pack_id, l.lemma, l.status)
                                    for l in s.get("links", [])
                                ],
                                created_at=started_at_db,
                                updated_at=completed_at_db,
                                generation_started_at=started_at_db,
                                generation_completed_at=completed_at_db,
                                generation_duration_ms=fixed_duration,
                                owner_user_id=self._owner_user_id,
                            )
                            s["llm_model"] = fixed_model or None
                            s["llm_params"] = fixed_params or None
                            if fixed_duration is not None:
                                s["generation_duration_ms"] = fixed_duration
                    except Exception:
                        # リペアは最終結果に影響しない（読み込みは既に成功している）
                        pass
                s.update(
                    {
                        "article_id": article_id,
                        "title_en": title_en,
                        "body_en": body_en,
                        "body_ja": body_ja,
                        "notes_ja": notes_ja,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                )
                logger.info(
                    "article_import_saved",
                    article_id=article_id,
                    title_len=len(title_en),
                    body_en_chars=len(body_en),
                    body_ja_chars=len(body_ja),
                    links=len(s.get("links", [])),
                )
                return s

            # ノード登録（役割別サブグラフ風の逐次構成）
            try:
                # StateGraph API 差異に耐える登録
                graph.add_node("generate_title", _generate_title)  # type: ignore[attr-defined]
                graph.add_node("generate_translation", _generate_translation)  # type: ignore[attr-defined]
                graph.add_node("generate_explanation", _generate_explanation)  # type: ignore[attr-defined]
                graph.add_node("generate_lemmas", _generate_lemmas)  # type: ignore[attr-defined]
                graph.add_node("filter_lemmas", _filter_lemmas)  # type: ignore[attr-defined]
                graph.add_node("link_or_create", _link_or_create_wordpacks)  # type: ignore[attr-defined]
                graph.add_node("save_article", _save_article)  # type: ignore[attr-defined]

                graph.set_entry_point("generate_title")  # type: ignore[attr-defined]
                graph.add_edge("generate_title", "generate_translation")  # type: ignore[attr-defined]
                graph.add_edge("generate_translation", "generate_explanation")  # type: ignore[attr-defined]
                graph.add_edge("generate_explanation", "generate_lemmas")  # type: ignore[attr-defined]
                graph.add_edge("generate_lemmas", "filter_lemmas")  # type: ignore[attr-defined]
                graph.add_edge("filter_lemmas", "link_or_create")  # type: ignore[attr-defined]
                graph.add_edge("link_or_create", "save_article")  # type: ignore[attr-defined]

                compiled = graph.compile()  # type: ignore[attr-defined]
                out_state = compiled.invoke(state)  # type: ignore[attr-defined]
                # 差分返却の場合でも初期stateを混ぜて欠落させない。ただし初期stateではなく、out_stateをそのまま優先。
                s = out_state if isinstance(out_state, dict) else state
                if isinstance(s, dict):
                    s.setdefault("llm_model", selected_llm_model)
                    s.setdefault("llm_params", formatted_llm_params)
                    s.setdefault("generation_category", generation_category)
                    s.setdefault("generation_started_at", generation_started_at)
            except Exception:
                # LangGraph が使えない/非互換のときは順次実行
                s = state
                s = _generate_title(s)
                s = _generate_translation(s)
                s = _generate_explanation(s)
                s = _generate_lemmas(s)
                s = _filter_lemmas(s)
                s = _link_or_create_wordpacks(s)
                # LLM 情報を state に反映
                try:
                    s["llm_model"] = getattr(req, "model", None) or settings.llm_model
                    s["llm_params"] = _fmt_llm_params()
                    s["generation_category"] = generation_category
                    if "generation_started_at" not in s:
                        s["generation_started_at"] = generation_started_at
                except Exception:
                    pass
                s = _save_article(s)
        except Exception:
            # グラフ初期化失敗時の最終フォールバック
            s = _ArticleState(original_text=original_text)
            s = _generate_title(s)  # type: ignore[name-defined]
            s = _generate_translation(s)  # type: ignore[name-defined]
            s = _generate_explanation(s)  # type: ignore[name-defined]
            s = _generate_lemmas(s)  # type: ignore[name-defined]
            s = _filter_lemmas(s)  # type: ignore[name-defined]
            s = _link_or_create_wordpacks(s)  # type: ignore[name-defined]
            # LLM 情報を state に反映
            try:
                s["llm_model"] = getattr(req, "model", None) or settings.llm_model
                s["llm_params"] = _fmt_llm_params()
                s["generation_category"] = generation_category
                if "generation_started_at" not in s:
                    s["generation_started_at"] = generation_started_at
            except Exception:
                pass
            s = _save_article(s)  # type: ignore[name-defined]

        # 最終応答は保存済みのDB値を読み直して返す（同期ズレ防止）。失敗時は明確にエラーを返す。
        try:
            # LangGraphの差分返却で state から key が落ちるケースに備え、閉包の saved_article_id を優先
            try:
                aid_local = locals().get("saved_article_id")  # type: ignore[assignment]
            except Exception:
                aid_local = None
            aid = str((aid_local or s.get("article_id") or ""))
            got = store.get_article(aid)
            if got is None:
                raise HTTPException(
                    status_code=500,
                    detail={
                        "message": "Failed to reload article after save",
                        "reason_code": "ARTICLE_DB_RELOAD_NONE",
                        "diagnostics": {"article_id": aid},
                    },
                )
            (
                title_en,
                body_en_db,
                body_ja_db,
                notes_ja_db,
                llm_model_db,
                llm_params_db,
                generation_category_db,
                created_at,
                updated_at,
                generation_started_at_db,
                generation_completed_at_db,
                generation_duration_ms_db,
                _guest_public_db,
                links,
            ) = got
            link_models: list[ArticleWordPackLink] = [
                ArticleWordPackLink(word_pack_id=wp, lemma=lm, status=st, is_empty=True)
                for (wp, lm, st) in links
            ]
            warning_map: dict[str, str] = {}
            try:
                warning_map = {
                    l.word_pack_id: str(l.warning)
                    for l in s.get("links", [])
                    if getattr(l, "warning", None)
                }
            except Exception:
                warning_map = {}
            # is_empty はUI用の推定のため簡易再判定
            try:
                for i, (wp, lm, st) in enumerate(links):
                    is_empty = True
                    try:
                        got_wp = store.get_word_pack(wp)
                        if got_wp is not None:
                            _, data_json, _, _ = got_wp
                            d = json.loads(data_json)
                            senses_empty = not d.get("senses")
                            ex = d.get("examples") or {}
                            examples_empty = all(
                                not (ex.get(k) or [])
                                for k in ["Dev", "CS", "LLM", "Business", "Common"]
                            )
                            study_empty = not bool((d.get("study_card") or "").strip())
                            is_empty = bool(
                                senses_empty and examples_empty and study_empty
                            )
                    except Exception:
                        is_empty = True
                    link_models[i].is_empty = is_empty
                    if warning_map.get(wp):
                        link_models[i].warning = warning_map[wp]
            except Exception:
                # is_empty の再計算に失敗しても致命ではない
                pass

            return ArticleDetailResponse(
                id=aid,
                title_en=title_en,
                body_en=body_en_db,
                body_ja=body_ja_db,
                notes_ja=(notes_ja_db or None),
                llm_model=(llm_model_db or None),
                llm_params=(llm_params_db or None),
                generation_category=(generation_category_db or None),
                related_word_packs=link_models,
                created_at=created_at,
                updated_at=updated_at,
                generation_started_at=(generation_started_at_db or None),
                generation_completed_at=(generation_completed_at_db or None),
                generation_duration_ms=(
                    int(generation_duration_ms_db)
                    if isinstance(generation_duration_ms_db, (int, float))
                    and not isinstance(generation_duration_ms_db, bool)
                    else None
                ),
                warnings=list(s.get("warnings", []) or []) or None,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Exception while reloading article after save",
                    "reason_code": "ARTICLE_DB_RELOAD_ERROR",
                    "diagnostics": {
                        "error": str(exc),
                        "article_id": str(s.get("article_id") or ""),
                    },
                },
            )
