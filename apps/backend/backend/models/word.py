from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..domain.wordpack.lemma import LEMMA_ALLOWED_PATTERN, validate_lemma
from ..llm_models import ensure_supported_llm_model
from .common import Citation, ConfidenceLevel


DEFAULT_ETYMOLOGY_PLACEHOLDER = "語源情報はまだ収集中です。"


def _validate_lemma(value: str) -> str:
    return validate_lemma(value)


class RegenerateScope(str, Enum):
    all = "all"
    examples = "examples"
    collocations = "collocations"


class WordPackCreateRequest(BaseModel):
    """Request model for creating an empty WordPack entry without generation.

    生成を行わず、空の各情報を持つ WordPack を保存するための最小入力。
    """

    lemma: str = Field(
        min_length=1,
        max_length=64,
        description="見出し語（1..64文字、英数字・半角スペース・ハイフン・アポストロフィのみ）",
    )

    @field_validator("lemma")
    @classmethod
    def ensure_lemma_safe(cls, value: str) -> str:
        return _validate_lemma(value)


class WordPackRequest(BaseModel):
    """Request model for generating a word pack (MVP).

    学習対象の語（lemma）と必要に応じて品詞などの条件を指定する。
    """

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "lemma": "converge",
                    "pronunciation_enabled": True,
                    "regenerate_scope": "all",
                    "model": "gpt-5.4-mini",
                    "reasoning": {"effort": "minimal"},
                    "text": {"verbosity": "medium"},
                },
                {
                    "lemma": "converge",
                    "pronunciation_enabled": False,
                    "regenerate_scope": "examples",
                    "model": "gpt-5.4-mini",
                    "reasoning": {"effort": "minimal"},
                    "text": {"verbosity": "medium"},
                },
                {
                    "lemma": "converge",
                    "regenerate_scope": "collocations",
                    "model": "gpt-5.4-nano",
                    "reasoning": {"effort": "minimal"},
                    "text": {"verbosity": "medium"},
                },
            ],
            "x-schema-version": "0.3.0",
        }
    )

    lemma: str = Field(
        min_length=1,
        max_length=64,
        description="見出し語（1..64文字、英数字・半角スペース・ハイフン・アポストロフィのみ）",
    )
    pos: str | None = None
    pronunciation_enabled: bool = True
    regenerate_scope: RegenerateScope = Field(
        default=RegenerateScope.all,
        description=(
            "再生成スコープ。MVPでは全体生成の上で、examples=例文セクション強化、"
            "collocations=共起セクションのみダミー加筆。"
        ),
    )
    # オプショナルな生成パラメータ（未指定ならバックエンド設定を使用）
    model: str | None = Field(
        default=None,
        description="LLMモデル名の上書き（未指定なら既定 settings.llm_model）",
    )
    reasoning: dict | None = Field(
        default=None,
        description="reasoning オプション（例: {effort: minimal|low|medium|high}）",
    )
    text: dict | None = Field(
        default=None, description="text オプション（例: {verbosity: low|medium|high}）"
    )

    @field_validator("lemma")
    @classmethod
    def ensure_lemma_safe(cls, value: str) -> str:
        return _validate_lemma(value)

    @field_validator("model")
    @classmethod
    def ensure_model_supported(cls, value: str | None) -> str | None:
        return ensure_supported_llm_model(value) if value else value


class Sense(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "id": "s1",
                    "gloss_ja": "意味（暫定）",
                    "definition_ja": "核となる定義を1〜2文で端的に示す。",
                    "nuances_ja": "フォーマル/口語/専門寄り等の含意や使い分け。",
                    "patterns": ["converge on N"],
                    "synonyms": ["gather", "meet"],
                    "antonyms": ["diverge"],
                    "register": "formal",
                    "notes_ja": "可算/不可算や自他/再帰などの注意点。",
                }
            ]
        },
    )

    id: str
    gloss_ja: str
    # よりボリューミーな語義のための追加フィールド（すべて任意）
    definition_ja: str | None = None
    nuances_ja: str | None = None
    # 名詞（特に専門用語）のときに概念解説を充実させる任意フィールド
    # term_overview_ja: 用語の概要（3〜5文程度）
    # term_core_ja: 用語の本質/本質的ポイント（1〜2文）
    term_overview_ja: str | None = None
    term_core_ja: str | None = None
    patterns: list[str] = Field(default_factory=list)
    synonyms: list[str] = Field(default_factory=list)
    antonyms: list[str] = Field(default_factory=list)
    # BaseModel の属性名と衝突するため、フィールド名を register_ に変更し、API 互換のためエイリアスを維持
    register_: str | None = Field(default=None, alias="register")
    notes_ja: str | None = None


class CollocationLists(BaseModel):
    verb_object: list[str] = Field(default_factory=list)
    adj_noun: list[str] = Field(default_factory=list)
    prep_noun: list[str] = Field(default_factory=list)


class Collocations(BaseModel):
    general: CollocationLists = Field(default_factory=CollocationLists)
    academic: CollocationLists = Field(default_factory=CollocationLists)


class ContrastItem(BaseModel):
    with_: str = Field(alias="with")
    diff_ja: str

    model_config = ConfigDict(populate_by_name=True)


class ExampleCategory(str, Enum):
    Dev = "Dev"
    CS = "CS"
    LLM = "LLM"
    Business = "Business"
    Common = "Common"


class Examples(BaseModel):
    class ExampleItem(BaseModel):
        en: str
        ja: str
        grammar_ja: str | None = None
        # 追加メタ: カテゴリと生成に使用した LLM 情報
        category: ExampleCategory | None = Field(
            default=None, description="例文カテゴリ（後方互換のため任意）"
        )
        llm_model: str | None = Field(
            default=None, description="例文生成に使用したLLMモデル名（任意）"
        )
        llm_params: str | None = Field(
            default=None, description="LLMパラメータ情報を連結した文字列（任意）"
        )
        checked_only_count: int = Field(
            default=0,
            ge=0,
            description="この例文を確認しただけの回数（非負整数）",
        )
        learned_count: int = Field(
            default=0,
            ge=0,
            description="この例文を学習完了と記録した回数（非負整数）",
        )
        transcription_typing_count: int = Field(
            default=0,
            ge=0,
            description="文字起こしトレーニングで入力された延べ文字数（非負整数）",
        )

    Dev: list[ExampleItem] = Field(default_factory=list)
    CS: list[ExampleItem] = Field(default_factory=list)
    LLM: list[ExampleItem] = Field(default_factory=list)
    Business: list[ExampleItem] = Field(default_factory=list)
    Common: list[ExampleItem] = Field(default_factory=list)


class Etymology(BaseModel):
    """語源メモ。欠落時はフォールバック文言を許容する。"""

    note: str | None = Field(
        default=None,
        description="語源の概要。空や None はフォールバック文言で補われる。",
    )
    confidence: ConfidenceLevel = ConfidenceLevel.low

    @field_validator("note", mode="after")
    @classmethod
    def normalize_note(cls, value: str | None) -> str | None:
        # 余分な空白を落とし、空文字は None として扱うことでレスポンス側のフォールバックを明示化する。
        if value is None:
            return None
        trimmed = str(value).strip()
        return trimmed or None


# --- Example listing API models ---
class ExampleListItem(BaseModel):
    id: int
    word_pack_id: str
    lemma: str
    category: ExampleCategory
    en: str
    ja: str
    grammar_ja: str | None = None
    created_at: str
    word_pack_updated_at: str | None = None
    checked_only_count: int = Field(
        default=0,
        ge=0,
        description="例文を確認しただけの回数（非負整数）",
    )
    learned_count: int = Field(
        default=0,
        ge=0,
        description="例文を学習済みと記録した回数（非負整数）",
    )
    transcription_typing_count: int = Field(
        default=0,
        ge=0,
        description="例文の文字起こし練習で積み上がった入力文字数",
    )


class ExampleListResponse(BaseModel):
    items: list[ExampleListItem]
    total: int
    limit: int
    offset: int


class ExampleTranscriptionTypingRequest(BaseModel):
    input_length: int = Field(
        ge=1,
        le=2000,
        description="文字起こしで入力された文字数（1〜2000の範囲）",
    )


class ExampleTranscriptionTypingResponse(BaseModel):
    transcription_typing_count: int = Field(
        ge=0,
        description="更新後の文字起こし入力累積文字数",
    )


class ExamplesBulkDeleteRequest(BaseModel):
    ids: list[int] = Field(
        default_factory=list,
        description="削除対象の例文ID一覧",
        min_length=1,
        max_length=200,
    )


class ExamplesBulkDeleteResponse(BaseModel):
    deleted: int = Field(description="削除に成功した件数")
    not_found: list[int] = Field(
        default_factory=list, description="削除できなかったID一覧（未存在など）"
    )


class Pronunciation(BaseModel):
    ipa_GA: str | None = None
    ipa_RP: str | None = None
    syllables: int | None = None
    stress_index: int | None = None
    linking_notes: list[str] = Field(default_factory=list)


class WordPack(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "lemma": "converge",
                    "sense_title": "収束ポイント",
                    "pronunciation": {
                        "ipa_GA": "/kənvɝdʒ/",
                        "syllables": 2,
                        "stress_index": 1,
                        "linking_notes": [],
                    },
                    "senses": [
                        {"id": "s1", "gloss_ja": "意味（暫定）", "patterns": []}
                    ],
                    "collocations": {
                        "general": {"verb_object": [], "adj_noun": [], "prep_noun": []},
                        "academic": {
                            "verb_object": [],
                            "adj_noun": [],
                            "prep_noun": [],
                        },
                    },
                    "contrast": [],
                    "examples": {
                        "Dev": [
                            {
                                "en": "converge example in app dev.",
                                "ja": "アプリ開発の現場での converge の例",
                                "grammar_ja": "第3文型。",
                            }
                        ],
                        "CS": [],
                        "LLM": [],
                        "Business": [],
                        "Common": [],
                    },
                    "etymology": {"note": "語源情報はまだ収集中です。", "confidence": "low"},
                    "study_card": "この語の要点（暫定）。",
                    "citations": [],
                    "confidence": "low",
                }
            ],
            "x-schema-version": "0.3.2",
        }
    )

    lemma: str
    sense_title: str = Field(
        default="",
        description="語義一覧などで表示する短い語義タイトル（10文字程度を想定）",
    )
    pronunciation: Pronunciation
    senses: list[Sense] = Field(default_factory=list)
    collocations: Collocations = Field(default_factory=Collocations)
    contrast: list[ContrastItem] = Field(default_factory=list)
    examples: Examples = Field(default_factory=Examples)
    etymology: Etymology
    study_card: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: ConfidenceLevel = ConfidenceLevel.low
    # 生成に使用したAIのメタ（任意）
    llm_model: str | None = Field(default=None)
    llm_params: str | None = Field(default=None)
    guest_public: bool = Field(
        default=False,
        description="ゲスト閲覧対象かどうか（WordPack単位の公開フラグ）",
    )
    checked_only_count: int = Field(
        default=0,
        ge=0,
        description="WordPack全体を確認しただけの回数（非負整数）",
    )
    learned_count: int = Field(
        default=0,
        ge=0,
        description="WordPack全体を学習した回数（非負整数）",
    )


class GeneratedWordPackResponse(WordPack):
    """生成直後の保存済みWordPack IDを含むレスポンス。"""

    id: str = Field(description="保存されたWordPack ID")


class WordPackListItem(BaseModel):
    """WordPack一覧表示用の軽量モデル"""

    id: str
    lemma: str
    sense_title: str = Field(default="", description="一覧表示用の語義タイトル")
    created_at: str
    updated_at: str
    is_empty: bool = Field(
        default=False, description="内容が空のWordPackかどうか（UI用）"
    )
    examples_count: dict | None = Field(
        default=None, description="カテゴリごとの例文数（UI用）"
    )
    checked_only_count: int = Field(
        default=0,
        ge=0,
        description="WordPack全体を確認しただけの回数（非負整数）",
    )
    learned_count: int = Field(
        default=0,
        ge=0,
        description="WordPack全体を学習した回数（非負整数）",
    )
    guest_public: bool = Field(
        default=False,
        description="ゲスト閲覧対象かどうか（WordPack単位の公開フラグ）",
    )


class WordPackListFacetCounts(BaseModel):
    """他の条件を保ったまま各絞り込みへ切り替えた場合の件数。"""

    public: int = Field(ge=0)
    private: int = Field(ge=0)
    generated: int = Field(ge=0)
    not_generated: int = Field(ge=0)


class WordPackListResponse(BaseModel):
    """WordPack一覧レスポンス"""

    items: list[WordPackListItem]
    total: int = Field(
        ge=0,
        description="現在の認可範囲にあるWordPackの総件数",
    )
    filtered_total: int = Field(
        ge=0,
        description="検索・絞り込み条件に一致する全ページ合計件数",
    )
    facet_counts: WordPackListFacetCounts
    limit: int
    offset: int


class WordPackGuestPublicRequest(BaseModel):
    guest_public: bool = Field(
        description="ゲスト閲覧対象として公開する場合は true",
    )


class WordPackGuestPublicResponse(BaseModel):
    word_pack_id: str = Field(description="更新対象のWordPack ID")
    guest_public: bool = Field(description="更新後のゲスト公開フラグ")


class StudyProgressRequest(BaseModel):
    kind: Literal["checked", "learned"] = Field(
        description="学習記録の種類: checked=確認のみ / learned=学習完了",
    )


class WordPackStudyProgressResponse(BaseModel):
    checked_only_count: int = Field(
        description="更新後の確認のみカウント",
        ge=0,
    )
    learned_count: int = Field(
        description="更新後の学習済みカウント",
        ge=0,
    )


class ExampleStudyProgressResponse(BaseModel):
    id: int = Field(description="対象の例文ID")
    word_pack_id: str = Field(description="例文が属するWordPack ID")
    checked_only_count: int = Field(
        description="更新後の確認のみカウント",
        ge=0,
    )
    learned_count: int = Field(
        description="更新後の学習済みカウント",
        ge=0,
    )


class WordPackRegenerateRequest(BaseModel):
    """WordPack再生成リクエスト"""

    pronunciation_enabled: bool = True
    regenerate_scope: RegenerateScope = Field(default=RegenerateScope.all)
    model: str | None = Field(
        default=None,
        description="LLMモデル名の上書き（未指定なら既定 settings.llm_model）",
    )
    reasoning: dict | None = Field(default=None)
    text: dict | None = Field(default=None)

    @field_validator("model")
    @classmethod
    def ensure_model_supported(cls, value: str | None) -> str | None:
        return ensure_supported_llm_model(value) if value else value
