from __future__ import annotations

from .base import (
    Any,
    EXAMPLE_CATEGORIES,
    FirestoreBaseRepository,
    Iterable,
    Mapping,
    Sequence,
    defaultdict,
    firestore,
    normalize_non_negative_int,
)
from .wordpacks import FirestoreWordPackRepository


class FirestoreExampleRepository(FirestoreBaseRepository):
    """例文に関する Firestore CRUD。"""

    def __init__(self, client: firestore.Client, wordpacks: FirestoreWordPackRepository):
        super().__init__(client)
        self._examples = client.collection("examples")
        self._wordpacks = wordpacks

    def _build_examples_query(
        self, *, word_pack_id: str | None = None, category: str | None = None
    ) -> firestore.Query | firestore.CollectionReference:
        """Create a query that narrows down examples by pack/category."""

        query: firestore.Query | firestore.CollectionReference = self._examples
        if word_pack_id:
            query = query.where("word_pack_id", "==", word_pack_id)
        if category:
            query = query.where("category", "==", category)
        return query

    def _apply_search_filters(
        self,
        query: firestore.Query | firestore.CollectionReference,
        *,
        search: str | None,
        search_mode: str,
    ) -> tuple[firestore.Query | firestore.CollectionReference, str | None]:
        """検索条件を Firestore の where 節で表現し、必要な order_by キーを返す。"""

        normalized = self._normalize_search_text(search)
        if not normalized:
            return query, None
        if search_mode == "prefix":
            upper_bound = normalized + "\uf8ff"
            query = query.where("search_en", ">=", normalized).where(
                "search_en", "<=", upper_bound
            )
            return query, "search_en"
        if search_mode == "suffix":
            reversed_query = normalized[::-1]
            upper_bound = reversed_query + "\uf8ff"
            query = query.where("search_en_reversed", ">=", reversed_query).where(
                "search_en_reversed", "<=", upper_bound
            )
            return query, "search_en_reversed"
        terms = self._extract_search_terms(normalized)
        if not terms:
            return query, None

        most_specific_term = max(terms, key=lambda term: (len(term), term))
        query = query.where("search_terms", "array_contains", most_specific_term)
        return query, None

    def _paginate_ordered_query(
        self,
        query: firestore.Query | firestore.CollectionReference,
        *,
        primary_order: str,
        secondary_order: str | None,
        direction: firestore.Query.DESCENDING | firestore.Query.ASCENDING,
        offset: int,
        limit: int,
    ) -> list[firestore.DocumentSnapshot]:
        """order_by + start_after + limit を組み合わせたページングを適用する。"""

        ordered = query.order_by(primary_order, direction=direction)
        if secondary_order and secondary_order != primary_order:
            ordered = ordered.order_by(secondary_order, direction=direction)
        ordered = ordered.order_by("__name__", direction=firestore.Query.ASCENDING)
        cursor: firestore.DocumentSnapshot | None = None
        if offset:
            cursor = None
            for snap in ordered.limit(offset).stream():
                cursor = snap
            if cursor is None:
                return []
            ordered = ordered.start_after(cursor)
        return list(ordered.limit(limit).stream())

    def _ordered_examples_query(
        self,
        query: firestore.Query | firestore.CollectionReference,
        *,
        primary_order: str,
        secondary_order: str | None,
        direction: firestore.Query.DESCENDING | firestore.Query.ASCENDING,
    ) -> firestore.Query:
        ordered = query.order_by(primary_order, direction=direction)
        if secondary_order and secondary_order != primary_order:
            ordered = ordered.order_by(secondary_order, direction=direction)
        return ordered.order_by("__name__", direction=firestore.Query.ASCENDING)

    def _normalize_example_snapshot(
        self, snapshot: firestore.DocumentSnapshot
    ) -> dict[str, Any]:
        """Convert snapshot data into a normalized dict for downstream use."""

        data = snapshot.to_dict() or {}
        entry = dict(data)
        entry["category"] = str(entry.get("category") or "")
        entry["position"] = int(entry.get("position") or 0)
        entry["word_pack_id"] = str(entry.get("word_pack_id") or "")
        example_id = entry.get("example_id")
        if example_id is None:
            raw_id = snapshot.id
            example_id = int(raw_id) if str(raw_id).isdigit() else raw_id
        entry["example_id"] = example_id
        return entry

    def update_example_study_progress(
        self, example_id: int, checked_increment: int, learned_increment: int
    ) -> tuple[str, int, int] | None:
        doc_ref = self._examples.document(str(example_id))
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        current_checked = normalize_non_negative_int(data.get("checked_only_count"))
        current_learned = normalize_non_negative_int(data.get("learned_count"))
        next_checked = max(0, current_checked + int(checked_increment))
        next_learned = max(0, current_learned + int(learned_increment))
        if next_checked != current_checked or next_learned != current_learned:
            doc_ref.update(
                {
                    "checked_only_count": next_checked,
                    "learned_count": next_learned,
                }
            )
        return (str(data.get("word_pack_id") or ""), next_checked, next_learned)

    def delete_example(self, word_pack_id: str, category: str, index: int) -> int | None:
        if index < 0:
            return None
        query = (
            self._build_examples_query(word_pack_id=word_pack_id, category=category)
            .order_by("position")
            .order_by("example_id")
        )
        category_docs = [
            self._normalize_example_snapshot(snapshot) for snapshot in query.stream()
        ]
        if index >= len(category_docs):
            return None
        target = category_docs[index]
        self._examples.document(str(target["example_id"])).delete()
        self._reindex_category(word_pack_id, category)
        self._refresh_category_counts(word_pack_id)
        return len(category_docs) - 1

    def delete_examples_by_ids(
        self, example_ids: Iterable[int]
    ) -> tuple[int, list[int]]:
        deleted = 0
        not_found: list[int] = []
        touched: set[tuple[str, str]] = set()
        for example_id in example_ids:
            doc_ref = self._examples.document(str(example_id))
            snapshot = doc_ref.get()
            if not snapshot.exists:
                try:
                    not_found.append(int(example_id))
                except (TypeError, ValueError):
                    pass
                continue
            data = snapshot.to_dict() or {}
            doc_ref.delete()
            deleted += 1
            touched.add((str(data.get("word_pack_id") or ""), str(data.get("category") or "")))
        for word_pack_id, category in touched:
            self._reindex_category(word_pack_id, category)
            self._refresh_category_counts(word_pack_id)
        return deleted, not_found

    def append_examples(
        self, word_pack_id: str, category: str, items: Sequence[Mapping[str, Any]]
    ) -> int:
        if not items:
            return 0
        last_snapshot = next(
            iter(
                self._build_examples_query(
                    word_pack_id=word_pack_id, category=category
                )
                .order_by("position", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            ),
            None,
        )
        last_position = (
            int((last_snapshot.to_dict() or {}).get("position") or -1)
            if last_snapshot is not None
            else -1
        )
        start_pos = last_position + 1
        now = self._now_iso()
        ids = self._wordpacks.reserve_example_ids(len(items))
        id_iter = iter(ids)
        pack_meta = self._wordpacks.get_word_pack_metadata(word_pack_id) or {}
        lemma_label = str(pack_meta.get("lemma_label") or "")
        sense_title = str(pack_meta.get("sense_title") or "")
        metadata = pack_meta.get("metadata") or {}
        owner_user_id = None
        if isinstance(metadata, Mapping):
            owner_raw = metadata.get("owner_user_id")
            owner_user_id = str(owner_raw).strip() if owner_raw else None
        inserted = 0
        for item in items:
            en = str((item or {}).get("en") or "").strip()
            ja = str((item or {}).get("ja") or "").strip()
            if not en or not ja:
                continue
            grammar_ja = str((item or {}).get("grammar_ja") or "").strip() or None
            llm_model = str((item or {}).get("llm_model") or "").strip() or None
            llm_params = str((item or {}).get("llm_params") or "").strip() or None
            checked_only_count = normalize_non_negative_int((item or {}).get("checked_only_count"))
            learned_count = normalize_non_negative_int((item or {}).get("learned_count"))
            transcription_typing = normalize_non_negative_int(
                (item or {}).get("transcription_typing_count")
            )
            doc_id = str(next(id_iter))
            self._examples.document(doc_id).set(
                {
                    "example_id": int(doc_id),
                    "word_pack_id": word_pack_id,
                    "category": category,
                    "position": start_pos + inserted,
                    "en": en,
                    "ja": ja,
                    "grammar_ja": grammar_ja,
                    "llm_model": llm_model,
                    "llm_params": llm_params,
                    "checked_only_count": checked_only_count,
                    "learned_count": learned_count,
                    "transcription_typing_count": transcription_typing,
                    "created_at": now,
                    "pack_updated_at": now,
                    "lemma": lemma_label,
                    "sense_title": sense_title,
                    "owner_user_id": owner_user_id,
                    **self._build_search_payload(en),
                }
            )
            inserted += 1
        self._refresh_category_counts(word_pack_id)
        self._wordpacks.update_word_pack_metadata(word_pack_id, updated_at=now)
        return inserted

    def count_examples(
        self,
        *,
        search: str | None = None,
        search_mode: str = "contains",
        category: str | None = None,
        word_pack_id: str | None = None,
        public_only: bool = False,
    ) -> int:
        base_query = self._build_examples_query(
            word_pack_id=word_pack_id, category=category
        )
        filtered_query, _order_hint = self._apply_search_filters(
            base_query, search=search, search_mode=search_mode
        )
        if public_only:
            pack_cache: dict[str, Mapping[str, Any]] = {}
            return sum(
                1
                for snapshot in filtered_query.stream()
                if self._example_snapshot_is_guest_public(snapshot, pack_cache)
            )
        try:
            aggregation = filtered_query.count().get()
        except AttributeError:
            aggregation = None
        else:
            return self._extract_count_from_aggregation(aggregation)
        return sum(1 for _ in filtered_query.stream())

    def list_examples(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        order_by: str = "created_at",
        order_dir: str = "desc",
        search: str | None = None,
        search_mode: str = "contains",
        category: str | None = None,
        word_pack_id: str | None = None,
        public_only: bool = False,
    ) -> list[
        tuple[int, str, str, str, str, str, str | None, str, str | None, int, int, int]
    ]:
        normalized_limit = max(0, int(limit))
        normalized_offset = max(0, int(offset))
        if normalized_limit == 0:
            return []

        direction = firestore.Query.DESCENDING
        if str(order_dir).lower() == "asc":
            direction = firestore.Query.ASCENDING

        order_map = {
            "created_at": "created_at",
            "pack_updated_at": "pack_updated_at",
            "lemma": "lemma",
            "category": "category",
        }
        requested_order = order_map.get(order_by, "created_at")
        base_query = self._build_examples_query(
            word_pack_id=word_pack_id, category=category
        )
        filtered_query, search_order = self._apply_search_filters(
            base_query, search=search, search_mode=search_mode
        )
        primary_order = search_order or requested_order
        if public_only:
            ordered_query = self._ordered_examples_query(
                filtered_query,
                primary_order=primary_order,
                secondary_order=requested_order if search_order else None,
                direction=direction,
            )
            pack_cache: dict[str, Mapping[str, Any]] = {}
            public_snapshots = [
                snapshot
                for snapshot in ordered_query.stream()
                if self._example_snapshot_is_guest_public(snapshot, pack_cache)
            ]
            snapshots = public_snapshots[
                normalized_offset : normalized_offset + normalized_limit
            ]
        else:
            snapshots = self._paginate_ordered_query(
                filtered_query,
                primary_order=primary_order,
                secondary_order=requested_order if search_order else None,
                direction=direction,
                offset=normalized_offset,
                limit=normalized_limit,
            )

        pack_cache: dict[str, Mapping[str, Any]] = {}
        results: list[
            tuple[int, str, str, str, str, str, str | None, str, str | None, int, int, int]
        ] = []
        for snapshot in snapshots:
            entry = self._normalize_example_snapshot(snapshot)
            pack_id = str(entry.get("word_pack_id") or "")
            if pack_id and pack_id not in pack_cache:
                pack_cache[pack_id] = (
                    self._wordpacks.get_word_pack_metadata(pack_id) or {}
                )
            meta = pack_cache.get(pack_id, {})
            if not entry.get("lemma") and meta:
                entry["lemma"] = meta.get("lemma_label")
            if meta and not entry.get("pack_updated_at"):
                entry["pack_updated_at"] = meta.get("updated_at")
            results.append(
                (
                    int(entry["example_id"]),
                    pack_id,
                    str(entry.get("lemma") or ""),
                    str(entry.get("category") or ""),
                    str(entry.get("en") or ""),
                    str(entry.get("ja") or ""),
                    entry.get("grammar_ja"),
                    str(entry.get("created_at") or ""),
                    str(entry.get("pack_updated_at") or ""),
                    normalize_non_negative_int(entry.get("checked_only_count")),
                    normalize_non_negative_int(entry.get("learned_count")),
                    normalize_non_negative_int(entry.get("transcription_typing_count")),
                )
            )
        return results

    def _example_snapshot_is_guest_public(
        self,
        snapshot: firestore.DocumentSnapshot,
        pack_cache: dict[str, Mapping[str, Any]],
    ) -> bool:
        entry = self._normalize_example_snapshot(snapshot)
        pack_id = str(entry.get("word_pack_id") or "")
        if not pack_id:
            return False
        if pack_id not in pack_cache:
            pack_cache[pack_id] = self._wordpacks.get_word_pack_metadata(pack_id) or {}
        metadata = pack_cache.get(pack_id, {}).get("metadata") or {}
        if not isinstance(metadata, Mapping):
            return False
        return bool(metadata.get("guest_public", False))

    def update_example_transcription_typing(
        self, example_id: int, input_length: int
    ) -> int | None:
        doc_ref = self._examples.document(str(example_id))
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        try:
            normalized_length = int(input_length)
        except (TypeError, ValueError) as exc:
            raise ValueError("input length must be convertible to int") from exc
        if normalized_length <= 0:
            raise ValueError("input length must be positive")
        expected_length = len(str(data.get("en") or ""))
        if abs(expected_length - normalized_length) > 10:
            raise ValueError("input length deviates from sentence length beyond tolerance")
        current = normalize_non_negative_int(data.get("transcription_typing_count"))
        updated = current + normalized_length
        doc_ref.update({"transcription_typing_count": updated})
        return updated

    def _examples_for_pack(self, word_pack_id: str) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        query = self._build_examples_query(word_pack_id=word_pack_id)
        for snapshot in query.stream():
            docs.append(self._normalize_example_snapshot(snapshot))
        return docs

    def _reindex_category(self, word_pack_id: str, category: str) -> None:
        query = (
            self._build_examples_query(word_pack_id=word_pack_id, category=category)
            .order_by("position")
            .order_by("example_id")
        )
        docs = [self._normalize_example_snapshot(snapshot) for snapshot in query.stream()]
        for new_pos, doc in enumerate(docs):
            self._examples.document(str(doc["example_id"])).update({"position": new_pos})

    def _refresh_category_counts(self, word_pack_id: str) -> None:
        counts = defaultdict(int)
        for doc in self._examples_for_pack(word_pack_id):
            counts[str(doc.get("category") or "Common")] += 1
        normalized = {cat: counts.get(cat, 0) for cat in EXAMPLE_CATEGORIES}
        self._wordpacks.update_word_pack_metadata(
            word_pack_id, category_counts=normalized
        )


FirestoreExampleStore = FirestoreExampleRepository

__all__ = ["FirestoreExampleRepository", "FirestoreExampleStore"]
