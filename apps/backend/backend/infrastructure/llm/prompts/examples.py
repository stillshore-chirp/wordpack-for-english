from __future__ import annotations

from ....models.word import ExampleCategory

EXAMPLE_WORD_COUNT_TARGET = 50
EXAMPLE_WORD_COUNT_TOLERANCE = 5
EXAMPLE_WORD_COUNT_MIN = EXAMPLE_WORD_COUNT_TARGET - EXAMPLE_WORD_COUNT_TOLERANCE
EXAMPLE_WORD_COUNT_MAX = EXAMPLE_WORD_COUNT_TARGET + EXAMPLE_WORD_COUNT_TOLERANCE


def examples_response_schema() -> dict[str, object]:
    return {
        "type": "object",
        "required": ["examples"],
        "properties": {
            "examples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["en", "ja", "grammar_ja"],
                    "properties": {
                        "en": {"type": "string", "minLength": 1},
                        "ja": {"type": "string", "minLength": 1},
                        "grammar_ja": {"type": "string", "minLength": 1},
                    },
                },
            }
        },
    }


def is_valid_examples_response(value: object) -> bool:
    if not isinstance(value, dict) or not isinstance(value.get("examples"), list):
        return False
    for item in value["examples"]:
        if not isinstance(item, dict):
            return False
        for field in ("en", "ja", "grammar_ja"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                return False
    return True


def examples_common_notes_text() -> str:
    return (
        "注意事項:\n"
        "- gloss_ja / definition_ja / nuances_ja / grammar_ja / notes_ja は日本語。\n"
        "- もし対象語が名詞（一般名詞/固有名詞）や専門用語である場合、\n"
        "  term_overview_ja（3〜5文の概要）と term_core_ja（3〜5文の本質）を必ず日本語で記述する。\n"
        "  名詞以外（動詞/形容詞など）の場合、これら2つのキーは省略してよい。\n"
        f"- 例文は自然で、約{EXAMPLE_WORD_COUNT_TARGET}語（±{EXAMPLE_WORD_COUNT_TOLERANCE}語）の英文にする。各英例文には必ず対象語（lemma）を含める。\n"
        "- 本リクエストでは Target category のみを生成し、件数は末尾の Override 指示に厳密に従う。\n"
        "- 各例文の grammar_ja は2段落の詳細解説にする：\n"
        "  1) 品詞分解：形態素/句を『／』で区切り、語の後に【品詞/統語役割】を付す。必要に応じて句の内部構造も『＝』で示す（例：I【代/主】／sent【動/過去】／the documents【名/目】／via email【前置詞句＝via(前)+email(名)：手段】／to ensure quick delivery【不定詞句＝to+ensure(動)+quick(形)+delivery(名)：目的】）。\n"
        "  2) 解説：文の核（S/V/O/C）、修飾関係（手段/目的/時/理由など）、冠詞・可算/不可算の扱い等を日本語で簡潔に説明。\n"
        "- 『動詞+前置詞』のような表層的ラベルだけの説明は禁止。具体的に機能・役割まで述べる。\n"
    )


def examples_category_notes_text(category: ExampleCategory) -> str:
    base_map: dict[ExampleCategory, str] = {
        ExampleCategory.Dev: (
            "カテゴリ別ガイドライン（Target のみに適用）：\n"
            "- Dev: ソフトウェア開発の文脈。実務的で具体、学術調は避ける。メジャーな題材だけでなく、マイナーな題材も含める。\n"
        ),
        ExampleCategory.CS: (
            "カテゴリ別ガイドライン（Target のみに適用）：\n"
            "- CS: 計算機科学の学術文脈。精密・中立・フォーマル。メジャーな題材だけでなく、マイナーな題材も含める。\n"
        ),
        ExampleCategory.LLM: (
            "カテゴリ別ガイドライン（Target のみに適用）：\n"
            "- LLM: 機械学習/LLM 文脈。用語は技術的/学術的に正確、マーケ調は避ける。メジャーな題材だけでなく、マイナーな題材も含める。\n"
        ),
        ExampleCategory.Business: (
            "カテゴリ別ガイドライン（Target のみに適用）：\n"
            "- Business: ビジネス文脈（関係者/指標/KPI/スケジュール/トレードオフ/調整/戦略/財務/マーケティング）。丁寧で簡潔、スラング禁止。メジャーな題材だけでなく、マイナーな題材も含める。\n"
        ),
        ExampleCategory.Common: (
            "カテゴリ別ガイドライン（Target のみに適用）：\n"
            "- Common: とても様々な日常会話（友人/同僚とのチャット・通話/待ち合わせ/日常の小さな出来事/小さなやり取り）。ビジネス/過度なフォーマル語彙は避け、軽い口語を適度に用いる（下品表現は不可）。\n"
        ),
    }
    text = base_map.get(category, "")
    if category is ExampleCategory.Common:
        text += (
            "- Common の英例文は“ビジネス英語ではなく”カジュアルな日常会話のトーンで。友達/家族/同僚との軽いチャット想定。丁寧すぎる表現やフォーマルな語彙（therefore, thus, regarding, via など）は避け、口語（gonna, kinda, hey などは過度に使いすぎない範囲で可）、よくあるシーン（メッセ/通話/待ち合わせ/日常の小さな出来事）を取り入れる。\n"
            "- Common は短い感嘆や相づち・依頼も自然に含めてよい（例: Could you shoot me a text?, Mind sending me the link?）。ただしスラングや下品な表現は避ける。\n"
        )
    return text


def build_examples_prompt(lemma: str, category: ExampleCategory, count: int) -> str:
    header = (
        "あなたは辞書編集者である。必ず JSON オブジェクト1件のみを返し、説明文は書かないこと。\n"
        "対象語: "
        f"{lemma}\n\n"
        "スキーマ（キーと型は完全一致させること）:\n"
        "{\n"
        '  "examples": [ { "en": "...", "ja": "...", "grammar_ja": "..." } ]\n'
        "}\n"
    )
    tail = (
        f"対象カテゴリ: {category.value}\n"
        "出力は JSON オブジェクト1件に厳密に限定し、説明文やコードフェンスを含めないこと。\n"
        f"上書き指示: 例文数は必ず {count} 件とする。\n"
    )
    return (
        header
        + examples_common_notes_text()
        + examples_category_notes_text(category)
        + "カテゴリ別ガイドラインは Target category のみに適用すること。\n"
        + tail
    )
