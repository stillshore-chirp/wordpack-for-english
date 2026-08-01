from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from ...sense_title import choose_sense_title

# WordPack 例文カテゴリの固定順序。UI/Firestore 双方で共有する。
EXAMPLE_CATEGORIES: tuple[str, ...] = ("Dev", "CS", "LLM", "Business", "Common")


def normalize_non_negative_int(value: Any) -> int:
    """与えられた値を非負整数に正規化する。

    数値の正規化を I/O 層から切り離すことで、Firestore やエミュレータには常に
    整合した値だけが保存される。学習進捗カウンタは UI のバグで負値が送られて
    しまうと再採番が破綻するため、ここでゼロ以上に矯正しておく。
    """

    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        return 0
    return ivalue if ivalue >= 0 else 0


def iter_example_rows(examples: Mapping[str, Any]) -> Iterable[tuple]:
    """例文ペイロードを正規化し、永続化層が扱いやすい行タプルへ変換する。"""

    for category in EXAMPLE_CATEGORIES:
        arr = examples.get(category)
        if not isinstance(arr, Sequence):
            continue
        for pos, item in enumerate(arr):
            if not isinstance(item, Mapping):
                continue
            en = str(item.get("en") or "").strip()
            ja = str(item.get("ja") or "").strip()
            if not en or not ja:
                continue
            grammar_ja = str(item.get("grammar_ja") or "").strip() or None
            llm_model = str(item.get("llm_model") or "").strip() or None
            llm_params = str(item.get("llm_params") or "").strip() or None
            generation_provenance = list(item.get("generation_provenance") or [])
            checked_only_count = normalize_non_negative_int(
                (item or {}).get("checked_only_count")
            )
            learned_count = normalize_non_negative_int((item or {}).get("learned_count"))
            transcription_typing_count = normalize_non_negative_int(
                (item or {}).get("transcription_typing_count")
            )
            yield (
                category,
                pos,
                en,
                ja,
                grammar_ja,
                llm_model,
                llm_params,
                generation_provenance,
                checked_only_count,
                learned_count,
                transcription_typing_count,
            )


def split_examples_from_payload(
    data: str | Mapping[str, Any]
) -> tuple[
    str,
    Mapping[str, Any] | None,
    str,
    list[str],
    tuple[int, int],
    tuple[str | None, str | None],
]:
    """WordPack 入力 JSON から例文部分を分離し、コア情報を返す。"""

    checked_only_count = 0
    learned_count = 0
    lemma_llm_model: str | None = None
    lemma_llm_params: str | None = None

    if isinstance(data, Mapping):
        parsed: Mapping[str, Any] = dict(data)
    else:
        try:
            parsed = json.loads(data) if data else {}
        except Exception:
            empty_json = json.dumps({}, ensure_ascii=False)
            return (
                data if isinstance(data, str) else empty_json,
                None,
                "",
                [],
                (checked_only_count, learned_count),
                (lemma_llm_model, lemma_llm_params),
            )
        if not isinstance(parsed, Mapping):
            empty_json = json.dumps({}, ensure_ascii=False)
            return (
                data if isinstance(data, str) else empty_json,
                None,
                "",
                [],
                (checked_only_count, learned_count),
                (lemma_llm_model, lemma_llm_params),
            )

    sense_title = ""
    sense_candidates: list[str] = []
    try:
        sense_title = str(parsed.get("sense_title") or "").strip()
    except Exception:
        sense_title = ""

    try:
        val = str(parsed.get("llm_model") or "").strip()
        lemma_llm_model = val or None
    except Exception:
        lemma_llm_model = None
    try:
        val = str(parsed.get("llm_params") or "").strip()
        lemma_llm_params = val or None
    except Exception:
        lemma_llm_params = None

    try:
        checked_only_count = normalize_non_negative_int(
            (parsed or {}).get("checked_only_count")
        )
    except Exception:
        checked_only_count = 0
    try:
        learned_count = normalize_non_negative_int((parsed or {}).get("learned_count"))
    except Exception:
        learned_count = 0

    senses_payload = parsed.get("senses") if isinstance(parsed, Mapping) else None
    if isinstance(senses_payload, Sequence):
        for sense in senses_payload:
            if not isinstance(sense, Mapping):
                continue
            for key in (
                "gloss_ja",
                "term_overview_ja",
                "term_core_ja",
                "definition_ja",
                "nuances_ja",
            ):
                try:
                    val = str(sense.get(key) or "").strip()
                except Exception:
                    val = ""
                if val:
                    sense_candidates.append(val)

    examples = parsed.get("examples") if isinstance(parsed, Mapping) else None
    if isinstance(examples, Mapping):
        core = dict(parsed)
        core.pop("examples", None)
        return (
            json.dumps(core, ensure_ascii=False),
            examples,
            sense_title,
            sense_candidates,
            (checked_only_count, learned_count),
            (lemma_llm_model, lemma_llm_params),
        )
    serialized = (
        json.dumps(parsed, ensure_ascii=False) if not isinstance(data, str) else data
    )
    return (
        serialized,
        None,
        sense_title,
        sense_candidates,
        (checked_only_count, learned_count),
        (lemma_llm_model, lemma_llm_params),
    )


def merge_core_with_examples(core_json: str, rows: Sequence[Mapping[str, Any]]) -> str:
    """WordPack 本体 JSON に例文一覧を合成して返す。"""

    try:
        core = json.loads(core_json) if core_json else {}
    except Exception:
        core = {}
    examples: dict[str, list[dict[str, Any]]] = {cat: [] for cat in EXAMPLE_CATEGORIES}
    for r in rows:
        category = r["category"]
        item: dict[str, Any] = {"en": r["en"], "ja": r["ja"]}
        if r.get("grammar_ja"):
            item["grammar_ja"] = r["grammar_ja"]
        if r.get("llm_model"):
            item["llm_model"] = r["llm_model"]
        if r.get("llm_params"):
            item["llm_params"] = r["llm_params"]
        if r.get("generation_provenance"):
            item["generation_provenance"] = list(r["generation_provenance"])
        item["checked_only_count"] = normalize_non_negative_int(
            r.get("checked_only_count")
        )
        item["learned_count"] = normalize_non_negative_int(r.get("learned_count"))
        item["transcription_typing_count"] = normalize_non_negative_int(
            r.get("transcription_typing_count")
        )
        examples.setdefault(category, []).append(item)
    for cat in EXAMPLE_CATEGORIES:
        examples.setdefault(cat, [])
    core["examples"] = examples
    return json.dumps(core, ensure_ascii=False)


def build_sense_title(
    lemma: str, sense_title_raw: str, sense_candidates: list[str]
) -> str:
    """Firestore 用に見出し語の日本語タイトルを決定する。"""

    return choose_sense_title(
        sense_title_raw,
        sense_candidates,
        lemma=lemma,
        limit=40,
    )
