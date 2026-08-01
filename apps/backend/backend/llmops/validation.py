from __future__ import annotations

import json

from ..infrastructure.llm.json_response_parser import parse_json_response


def parse_article_lemmas(raw: str) -> tuple[list[str], bool, bool]:
    """記事lemma JSONの適用値・構文成功・宣言スキーマ成功を返す。"""

    try:
        data = parse_json_response(str(raw), prefer_json_object=False)
    except Exception:
        return [], False, False

    schema_valid = isinstance(data, list) and all(
        isinstance(item, str) for item in data
    )
    if isinstance(data, list):
        return [str(item) for item in data], True, schema_valid
    if isinstance(data, dict) and isinstance(data.get("lemmas"), list):
        # 既存レスポンスとの互換性は保つが、宣言した配列スキーマの成功とは記録しない。
        return [str(item) for item in data.get("lemmas", [])], True, False
    return [], True, False


def parse_category_lemma(raw: str) -> tuple[str, bool, bool]:
    """カテゴリ選択JSONの適用値・構文成功・宣言スキーマ成功を返す。"""

    try:
        data = json.loads((raw or "").strip().strip("`"))
    except (json.JSONDecodeError, TypeError):
        return "", False, False
    if not isinstance(data, dict) or not isinstance(data.get("lemma"), str):
        return "", True, False
    return data["lemma"].strip(), True, True
