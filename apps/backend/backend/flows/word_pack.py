from __future__ import annotations

"""WordPack 生成フロー。backend.providers のモジュラ構造を前提に動作する。"""

import json
from typing import Any

from pydantic import ValidationError

from . import create_state_graph

from ..infrastructure.llm.json_response_parser import parse_json_response
from ..infrastructure.llm.prompts.examples import build_examples_prompt
from ..infrastructure.llm.prompts.wordpack import build_wordpack_prompt
from ..llmops.completion import complete_typed, safe_provenance, with_validation
from ..llmops.identity import prompt_identity_from_builder
from ..models.word import (
    DEFAULT_ETYMOLOGY_PLACEHOLDER,
    WordPack,
    Sense,
    Collocations,
    CollocationLists,
    Etymology,
    Pronunciation,
    Examples,
    ContrastItem,
    RegenerateScope,
    ExampleCategory,
)
from ..models.common import ConfidenceLevel, Citation
from ..config import settings
from ..logging import logger
from ..pronunciation import generate_pronunciation
from ..sense_title import choose_sense_title


# --- 例文生成プロンプト: Notes 分割（共通/カテゴリ別） ---
class WordPackFlow:
    """Word pack generation flow (no dummy outputs).

    単語学習パックを生成するフロー。ダミー生成は行わず、取得できない情報は
    可能な限り空（未設定）で返す。strict モードでは不正な生成結果はエラーを送出する。
    """

    def __init__(
        self,
        chroma_client: Any | None = None,
        *,
        llm: Any | None = None,
        llm_info: dict[str, Any] | None = None,
    ) -> None:
        """ベクトルDB クライアントを受け取り、LangGraph を初期化。

        Parameters
        ----------
        chroma_client: Any | None
            語義・共起取得などの検索に利用するクライアント（任意）。
        """
        self.chroma = chroma_client
        self.llm = llm
        # 生成に使用した LLM のメタ（モデル名やパラメータ文字列表現）
        self._llm_info: dict[str, Any] = llm_info or {}
        self._generation_provenance: list[dict[str, Any]] = []
        self.graph = create_state_graph()

    @property
    def generation_provenance(self) -> list[dict[str, Any]]:
        return list(self._generation_provenance)

    def _lookup_etymology_from_dictionary(self, lemma: str) -> str | None:
        """静的な辞書ソースから語源メモを探すフォールバック。"""

        dictionary: dict[str, str] = {
            "converge": "From Latin convergere ('to incline together').",
            "novel": "From Latin novellus, meaning 'new' or 'fresh'.",
        }
        return dictionary.get(lemma.lower().strip())

    def _build_etymology(
        self, lemma: str, llm_payload: dict[str, Any] | None
    ) -> Etymology:
        """LLM 出力と辞書参照を統合し、欠落時はプレースホルダーを返す。"""

        note: str | None = None
        confidence = ConfidenceLevel.low

        if isinstance(llm_payload, dict):
            try:
                ety = llm_payload.get("etymology") or {}
                note_candidate = str(ety.get("note") or "").strip()
                if note_candidate:
                    note = note_candidate
                conf = str(ety.get("confidence") or "low").strip().lower()
                if conf in {"medium", "med"}:
                    confidence = ConfidenceLevel.medium
                elif conf in {"high", "hi"}:
                    confidence = ConfidenceLevel.high
            except Exception:
                # 破損した形でも必ずフォールバックするため握りつぶす
                pass

        dictionary_note = self._lookup_etymology_from_dictionary(lemma)
        if note is None and dictionary_note:
            note = dictionary_note
            confidence = ConfidenceLevel.medium

        resolved_note = note or DEFAULT_ETYMOLOGY_PLACEHOLDER
        return Etymology(note=resolved_note, confidence=confidence)

    # --- 発音推定（cmudict/g2p-en 利用、フォールバック付き） ---
    def _generate_pronunciation(self, lemma: str) -> Pronunciation:
        return generate_pronunciation(lemma)

    def _retrieve(self, lemma: str) -> dict[str, Any]:
        """語の情報を取得。OpenAI LLM を使用してセクション別のJSONを生成・解析。"""
        citations: list[Citation] = []
        llm_data: dict[str, Any] | None = None

        # OpenAI LLM を使用して語の詳細情報を生成
        try:
            if self.llm is not None and hasattr(self.llm, "complete"):
                logger.info("wordpack_llm_prompt_built", lemma=lemma)
                prompt = build_wordpack_prompt(lemma)
                identity = prompt_identity_from_builder(
                    prompt_id="wordpack.core",
                    operation="wordpack.generate",
                    builder=build_wordpack_prompt,
                    schema=WordPack.model_json_schema(),
                    major_settings=self._llm_info,
                )
                completion = complete_typed(
                    self.llm,
                    prompt,
                    identity=identity,
                    response_mode="json",
                )
                out = completion.content
                logger.info(
                    "wordpack_llm_output_received",
                    lemma=lemma,
                    output_chars=len(out or ""),
                )
                if isinstance(out, str) and out.strip():
                    try:
                        llm_data = parse_json_response(out)
                        has_senses = bool(
                            isinstance(llm_data, dict)
                            and isinstance(llm_data.get("senses"), list)
                            and llm_data.get("senses")
                        )
                        schema_valid = False
                        if isinstance(llm_data, dict):
                            try:
                                WordPack.model_validate({**llm_data, "lemma": lemma})
                                schema_valid = True
                            except ValidationError:
                                logger.info(
                                    "wordpack_llm_schema_validation_failed",
                                    lemma=lemma,
                                )
                        completion = with_validation(
                            completion,
                            parse=True,
                            schema=schema_valid,
                            application=has_senses,
                        )
                        logger.info(
                            "wordpack_llm_json_parsed",
                            lemma=lemma,
                            has_senses=isinstance(llm_data.get("senses"), list),
                        )
                        citations.append(
                            Citation(
                                text=f"LLM-generated information for {lemma}",
                                meta={"source": "openai_llm", "word": lemma},
                            )
                        )
                    except json.JSONDecodeError:
                        completion = with_validation(
                            completion,
                            parse=False,
                            schema=False,
                            application=False,
                        )
                        logger.info("wordpack_llm_json_parse_failed", lemma=lemma)
                        citations.append(
                            Citation(
                                text=out.strip(),
                                meta={"source": "openai_llm", "word": lemma},
                            )
                        )
                        if settings.strict_mode:
                            raise RuntimeError(
                                "Failed to parse LLM JSON in strict mode"
                            )
                else:
                    completion = with_validation(
                        completion,
                        parse=False,
                        schema=False,
                        application=False,
                    )
                provenance = safe_provenance(completion)
                if provenance is not None:
                    self._generation_provenance.append(provenance)
        except Exception as exc:
            if settings.strict_mode:
                # strict: LLM 呼び出し失敗/タイムアウトは即エラー
                raise
            # 非 strict では静かにフォールバック

        # strict: LLM 出力が空/未解析ならエラー
        if settings.strict_mode and (
            llm_data is None
            or (isinstance(llm_data, dict) and not llm_data.get("senses"))
        ):
            raise RuntimeError("LLM returned no usable data (strict mode)")

        return {"lemma": lemma, "citations": citations, "llm_data": llm_data}

    def _synthesize(
        self,
        lemma: str,
        *,
        pronunciation_enabled: bool = True,
        regenerate_scope: RegenerateScope | str = RegenerateScope.all,
        citations: list[Citation] | None = None,
    ) -> WordPack:
        """取得結果を整形し `WordPack` を構成。OpenAI LLM の情報を使用。"""
        logger.info("wordpack_synthesize_start", lemma=lemma)
        pronunciation = (
            self._generate_pronunciation(lemma)
            if pronunciation_enabled
            else Pronunciation(
                ipa_GA=None,
                ipa_RP=None,
                syllables=None,
                stress_index=None,
                linking_notes=[],
            )
        )

        # 初期値
        senses: list[Sense] = []
        collocations = Collocations()
        examples = Examples()
        sense_title_raw = ""
        etymology = Etymology(
            note=DEFAULT_ETYMOLOGY_PLACEHOLDER, confidence=ConfidenceLevel.low
        )
        study_card = ""

        # citations からは信頼度判断のみ。構造化は llm_data を優先
        confidence = ConfidenceLevel.low
        if citations:
            confidence = ConfidenceLevel.medium
        # LLMが使用されている場合は最低でもmedium
        if self.llm is not None and hasattr(self.llm, "complete"):
            confidence = ConfidenceLevel.medium

        # 直近の _retrieve の結果を graph/state 経由ではなく run から受け取れないため、
        # 呼び出し側で渡される citations のみを基準にしつつ、RP は LLM データに含まれる場合だけ上書き
        # 呼び出し元から llm_data は直接渡していないので、_retrieve の戻りを run 経由で受けるよう run を拡張
        # このメソッドは run から適切に llm_data を渡されることを前提とする（後段で run を修正）。
        # 型: citations 引数はそのまま使用。

        # 既存引数に llm_data を追加できないため、暫定として self に一時格納された値を見る
        llm_payload: dict[str, Any] | None = getattr(self, "_last_llm_data", None)

        if isinstance(llm_payload, dict):
            # senses
            try:
                s_list = llm_payload.get("senses") or []
                tmp_senses: list[Sense] = []
                for idx, s in enumerate(s_list):
                    if not isinstance(s, dict):
                        continue
                    gid = str(s.get("id") or f"s{idx + 1}")
                    gloss_ja = str(s.get("gloss_ja") or "").strip()
                    if not gloss_ja:
                        continue
                    patterns = [
                        str(p) for p in (s.get("patterns") or []) if str(p).strip()
                    ]
                    register = s.get("register")
                    definition_ja = str(s.get("definition_ja") or "").strip() or None
                    nuances_ja = str(s.get("nuances_ja") or "").strip() or None
                    synonyms = [
                        str(x) for x in (s.get("synonyms") or []) if str(x).strip()
                    ]
                    antonyms = [
                        str(x) for x in (s.get("antonyms") or []) if str(x).strip()
                    ]
                    notes_ja = str(s.get("notes_ja") or "").strip() or None
                    tmp_senses.append(
                        Sense(
                            id=gid,
                            gloss_ja=gloss_ja,
                            definition_ja=definition_ja,
                            nuances_ja=nuances_ja,
                            patterns=patterns,
                            synonyms=synonyms,
                            antonyms=antonyms,
                            register_=register,
                            notes_ja=notes_ja,
                            term_overview_ja=(
                                str(s.get("term_overview_ja") or "").strip() or None
                            ),
                            term_core_ja=(
                                str(s.get("term_core_ja") or "").strip() or None
                            ),
                        )
                    )
                if tmp_senses:
                    senses = tmp_senses
                    confidence = ConfidenceLevel.high
                logger.info(
                    "wordpack_senses_built", lemma=lemma, senses_count=len(senses)
                )
            except Exception:
                logger.info("wordpack_senses_build_error", lemma=lemma)
                pass

            # sense_title
            try:
                st_raw = str(llm_payload.get("sense_title") or "").strip()
                if st_raw:
                    sense_title_raw = st_raw
            except Exception:
                pass

            # collocations
            try:
                col = llm_payload.get("collocations") or {}

                def _lists(src: dict[str, Any]) -> CollocationLists:
                    return CollocationLists(
                        verb_object=[
                            str(x)
                            for x in (src.get("verb_object") or [])
                            if str(x).strip()
                        ],
                        adj_noun=[
                            str(x)
                            for x in (src.get("adj_noun") or [])
                            if str(x).strip()
                        ],
                        prep_noun=[
                            str(x)
                            for x in (src.get("prep_noun") or [])
                            if str(x).strip()
                        ],
                    )

                collocations = Collocations(
                    general=_lists(col.get("general") or {}),
                    academic=_lists(col.get("academic") or {}),
                )
            except Exception:
                pass

            # contrast
            contrast_items: list[ContrastItem] = []
            try:
                for it in llm_payload.get("contrast") or []:
                    if isinstance(it, dict):
                        w = str(it.get("with") or "").strip()
                        d = str(it.get("diff_ja") or "").strip()
                        if w and d:
                            contrast_items.append(ContrastItem(with_=w, diff_ja=d))
            except Exception:
                pass

            # examples: 初期生成でも追加生成でも同一のプロンプト/処理系を使う
            try:
                # デフォルト計画（将来の拡張に備えて集中管理）
                plan: dict[ExampleCategory, int] = {
                    ExampleCategory.Dev: 2,
                    ExampleCategory.CS: 2,
                    ExampleCategory.LLM: 2,
                    ExampleCategory.Business: 2,
                    ExampleCategory.Common: 2,
                }
                gen = self.generate_examples_for_categories(lemma, plan)
                examples = Examples(
                    Dev=gen.get(ExampleCategory.Dev, []),
                    CS=gen.get(ExampleCategory.CS, []),
                    LLM=gen.get(ExampleCategory.LLM, []),
                    Business=gen.get(ExampleCategory.Business, []),
                    Common=gen.get(ExampleCategory.Common, []),
                )
                logger.info(
                    "wordpack_examples_built_unified",
                    lemma=lemma,
                    Dev=len(examples.Dev),
                    CS=len(examples.CS),
                    LLM=len(examples.LLM),
                    Business=len(examples.Business),
                    Common=len(examples.Common),
                )
            except Exception as exc:
                # 統合フローのみを使用（旧ロジックのサルベージは廃止）
                logger.info(
                    "wordpack_examples_build_error_unified", lemma=lemma, error=str(exc)
                )
                examples = Examples()

            # study_card
            try:
                sc = str(llm_payload.get("study_card") or "").strip()
                if sc:
                    study_card = sc
            except Exception:
                pass

            # pronunciation (RP only; GA は内部生成を使用)
            try:
                pr = llm_payload.get("pronunciation") or {}
                rp = str(pr.get("ipa_RP") or "").strip()
                if rp:
                    pronunciation.ipa_RP = rp
            except Exception:
                pass

        sense_candidates: list[str] = []
        for sense in senses:
            sense_candidates.extend(
                [
                    sense.gloss_ja,
                    sense.term_overview_ja or "",
                    sense.term_core_ja or "",
                    sense.definition_ja or "",
                    sense.nuances_ja or "",
                ]
            )

        sense_title = choose_sense_title(
            sense_title_raw,
            sense_candidates,
            lemma=lemma,
            limit=20,
        )

        # 語源情報は LLM→辞書の順で補完し、欠落を許さない
        etymology = self._build_etymology(lemma, llm_payload)

        pack = WordPack(
            lemma=lemma,
            sense_title=sense_title,
            pronunciation=pronunciation,
            senses=senses,
            collocations=collocations,
            contrast=contrast_items if "contrast_items" in locals() else [],
            examples=examples,
            etymology=etymology,
            study_card=study_card,
            citations=citations or [],
            confidence=confidence,
            generation_provenance=list(self._generation_provenance),
        )
        logger.info(
            "wordpack_synthesize_done",
            lemma=lemma,
            senses_count=len(pack.senses),
            examples_total=(
                len(pack.examples.Dev)
                + len(pack.examples.CS)
                + len(pack.examples.LLM)
                + len(pack.examples.Business)
                + len(pack.examples.Common)
            ),
            has_definition_any=any(bool(s.definition_ja) for s in pack.senses),
            sense_title_len=len(pack.sense_title or ""),
        )
        # 厳格モードでは、語義と例文がともにゼロの場合はエラーとして扱う（ダミーを返さない）
        try:
            from ..config import settings as _settings  # 局所importで循環回避
        except Exception:
            _settings = None  # type: ignore[assignment]
        if _settings and getattr(_settings, "strict_mode", False):
            total_examples = (
                len(pack.examples.Dev)
                + len(pack.examples.CS)
                + len(pack.examples.LLM)
                + len(pack.examples.Business)
                + len(pack.examples.Common)
            )
            if len(pack.senses) == 0 and total_examples == 0:
                # 例外クラスをローカル定義（ルータ側で詳細HTTPにマップ）
                class WordPackGenerationError(RuntimeError):
                    def __init__(
                        self,
                        message: str,
                        *,
                        reason_code: str,
                        diagnostics: dict[str, object],
                    ):
                        super().__init__(message)
                        self.reason_code = reason_code
                        self.diagnostics = diagnostics

                raise WordPackGenerationError(
                    "No senses or examples generated",
                    reason_code="EMPTY_CONTENT",
                    diagnostics={
                        "lemma": lemma,
                        "senses_count": 0,
                        "examples_counts": {
                            "Dev": len(examples.Dev),
                            "CS": len(examples.CS),
                            "LLM": len(examples.LLM),
                            "Business": len(examples.Business),
                            "Common": len(examples.Common),
                        },
                    },
                )
        return pack

    def run(
        self,
        lemma: str,
        *,
        pronunciation_enabled: bool = True,
        regenerate_scope: RegenerateScope | str = RegenerateScope.all,
    ) -> WordPack:
        """語を入力として `WordPack` を生成して返す（ダミー生成なし）。"""
        self._generation_provenance = []
        data = self._retrieve(lemma)
        # 後続の _synthesize で LLM 生成物を参照できるように一時保存
        self._last_llm_data = data.get("llm_data")
        return self._synthesize(
            lemma,
            pronunciation_enabled=pronunciation_enabled,
            regenerate_scope=regenerate_scope,
            citations=data.get("citations"),
        )

    # --- Unified examples generation (initial/additional) ---
    def _build_examples_prompt(
        self, lemma: str, category: ExampleCategory, count: int
    ) -> str:
        """添付プロンプト（正）をパーツ化し、例文のみを要求するプロンプトを構築する。

        - 本文の英語ヘッダと Notes/ガイドラインは原型を維持
        - 例文スキーマは examples 配列のみ
        - 件数は既定の記述を尊重しつつ、最後に count 件のオーバーライド制約を追加
        """
        prompt = build_examples_prompt(lemma, category, count)
        # プロンプト長だけをログ（全文は Langfuse オプションで別途制御）
        try:
            logger.info(
                "wordpack_examples_prompt_built",
                lemma=lemma,
                category=category.value,
                count=count,
                prompt_chars=len(prompt),
            )
        except Exception:
            pass
        return prompt

    def _parse_examples_json(self, raw: str) -> list[dict[str, str]]:
        try:
            obj = parse_json_response(raw or "", prefer_json_object=False)
        except json.JSONDecodeError as exc:
            # LLM からの出力が JSON として壊れている場合は、上流に 500 を伝播させずに
            # 「例文ゼロ」として扱う。呼び出し側では len(items) < required で 502 等へ
            # マッピングされる設計のため、ここではログのみ残して空配列を返す。
            logger.warning(
                "wordpack_examples_json_parse_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                raw_chars=len(str(raw or "")),
            )
            return []
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(
                "wordpack_examples_json_parse_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                raw_chars=len(str(raw or "")),
            )
            return []
        if isinstance(obj, list):
            return [x for x in obj if isinstance(x, dict)]
        if isinstance(obj, dict) and isinstance(obj.get("examples"), list):
            return [x for x in obj.get("examples") if isinstance(x, dict)]
        # 形は不正だが JSON としては読めるケースも、例文ゼロ扱いにフォールバックする。
        logger.warning(
            "wordpack_examples_json_invalid_shape",
            obj_type=type(obj).__name__,
            raw_chars=len(str(raw or "")),
        )
        return []

    def generate_examples_for_categories(
        self, lemma: str, plan: dict[ExampleCategory, int]
    ) -> dict[ExampleCategory, list[Examples.ExampleItem]]:
        """カテゴリごとの要求数に従って例文を生成する。

        WordPack 本体の生成フローは LangGraph 初期化を維持するが、例文生成は
        カテゴリごとの独立した LLM 呼び出しであり、逐次実行の方が停止条件を明確に保てる。
        """
        results: dict[ExampleCategory, list[Examples.ExampleItem]] = {
            k: [] for k in plan.keys()
        }
        model_name = str(self._llm_info.get("model") or "").strip() or None
        params_str = str(self._llm_info.get("params") or "").strip() or None

        for cat, num in plan.items():
            prompt = self._build_examples_prompt(lemma, cat, int(num))
            identity = prompt_identity_from_builder(
                prompt_id=f"wordpack.examples.{cat.value.lower()}",
                operation=f"wordpack.examples.{cat.value.lower()}",
                builder=build_examples_prompt,
                schema={
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["en", "ja", "grammar_ja"],
                    },
                },
                major_settings={**self._llm_info, "category": cat.value, "count": int(num)},
            )
            if self.llm is None:
                out = "{}"
                completion = None
            else:
                completion = complete_typed(
                    self.llm,
                    prompt,
                    identity=identity,
                    response_mode="json",
                )
                out = completion.content
            parsed = self._parse_examples_json(out if isinstance(out, str) else "{}")
            items: list[Examples.ExampleItem] = []
            for it in parsed[: int(num)]:
                en = str(it.get("en") or "").strip()
                ja = str(it.get("ja") or "").strip()
                if not en or not ja:
                    continue
                grammar_ja = str(it.get("grammar_ja") or "").strip() or None
                items.append(
                    Examples.ExampleItem(
                        en=en,
                        ja=ja,
                        grammar_ja=grammar_ja,
                        category=cat,
                        llm_model=model_name,
                        llm_params=params_str,
                        generation_provenance=[],
                    )
                )
            results[cat] = items
            if completion is not None:
                completion = with_validation(
                    completion,
                    parse=bool(parsed),
                    schema=bool(parsed),
                    application=len(items) == int(num),
                )
                provenance = safe_provenance(completion)
                if provenance is not None:
                    self._generation_provenance.append(provenance)
                    for item in items:
                        item.generation_provenance = [provenance]
        return results
