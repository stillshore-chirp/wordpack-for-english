from __future__ import annotations

from .base import (
    AlreadyExists,
    Any,
    EXAMPLE_CATEGORIES,
    FirestoreBaseRepository,
    Lock,
    Mapping,
    Sequence,
    firestore,
    gexc,
    json,
    logger,
    normalize_non_negative_int,
    split_examples_from_payload,
    build_sense_title,
    merge_core_with_examples,
    iter_example_rows,
    uuid,
)


class FirestoreWordPackRepository(FirestoreBaseRepository):
    """WordPack 本体と lemma 情報を Firestore で管理する。"""

    _EXAMPLE_DELETE_BATCH_SIZE = 450
    _WORD_PACK_LOOKUP_RETRIES = 1

    def __init__(self, client: firestore.Client):
        super().__init__(client)
        self._lemmas = client.collection("lemmas")
        self._word_packs = client.collection("word_packs")
        self._examples = client.collection("examples")
        self._metadata = client.collection("metadata")
        # lemma upsert の局所衝突を避けるための簡易ロック
        self._lemma_write_lock = Lock()

    def _ordered_word_pack_query(self) -> firestore.Query:
        """Builds a deterministic descending query for word_packs collection."""

        return self._word_packs.order_by(
            "created_at", direction=firestore.Query.DESCENDING
        )

    def _fetch_word_pack_snapshots(
        self, limit: int, offset: int
    ) -> list[firestore.DocumentSnapshot]:
        """Apply limit/offset on Firestore side and fetch matching snapshots."""

        normalized_limit = max(0, int(limit))
        normalized_offset = max(0, int(offset))
        if normalized_limit == 0:
            return []
        query = self._ordered_word_pack_query()
        if normalized_offset:
            query = query.offset(normalized_offset)
        query = query.limit(normalized_limit)
        return list(query.stream())

    def save_word_pack(
        self,
        word_pack_id: str,
        lemma: str,
        data: str,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        now = self._now_iso()
        (
            core_json,
            examples,
            sense_title_raw,
            sense_candidates,
            (checked_only_count, learned_count),
            (lemma_llm_model, lemma_llm_params),
        ) = split_examples_from_payload(data)
        sense_title = build_sense_title(lemma, sense_title_raw, sense_candidates)
        lemma_id = self._upsert_lemma(
            label=lemma,
            sense_title=sense_title,
            llm_model=lemma_llm_model,
            llm_params=lemma_llm_params,
            now=now,
        )
        pack_ref = self._word_packs.document(word_pack_id)
        existing = pack_ref.get()
        existing_data = existing.to_dict() or {}
        existing_examples_total, counts_confident = self._extract_example_total(existing_data)
        # なぜ: 既存 metadata を保持しつつ guest_demo などの識別情報だけを差し替えたい。
        #      省略時に metadata が消えると、ゲストデータ判定が不安定になるため。
        existing_metadata = existing_data.get("metadata") or {}
        metadata_payload: Mapping[str, Any] | None = None
        if metadata is None:
            if isinstance(existing_metadata, Mapping) and existing_metadata:
                metadata_payload = dict(existing_metadata)
        else:
            metadata_payload = (
                {**existing_metadata, **metadata}
                if isinstance(existing_metadata, Mapping)
                else dict(metadata)
            )
        owner_user_id = None
        if isinstance(metadata_payload, Mapping):
            owner_raw = metadata_payload.get("owner_user_id")
            owner_user_id = str(owner_raw).strip() if owner_raw else None
        created_at = (
            str(existing_data.get("created_at") or now) if existing.exists else now
        )
        category_counts = self._replace_examples(
            word_pack_id,
            lemma=lemma,
            sense_title=sense_title,
            examples=examples,
            updated_at=now,
            existing_example_total=existing_examples_total,
            is_total_confident=counts_confident,
            owner_user_id=owner_user_id,
        )
        payload = {
            "lemma_id": lemma_id,
            "lemma_label": lemma,
            "lemma_label_lower": lemma.lower(),
            "sense_title": sense_title,
            "lemma_llm_model": lemma_llm_model,
            "lemma_llm_params": lemma_llm_params,
            "data_core": core_json,
            "created_at": created_at,
            "updated_at": now,
            "checked_only_count": normalize_non_negative_int(checked_only_count),
            "learned_count": normalize_non_negative_int(learned_count),
            "examples_category_counts": category_counts,
        }
        if metadata_payload is not None:
            payload["metadata"] = metadata_payload
        pack_ref.set(payload)

    def get_word_pack(self, word_pack_id: str) -> tuple[str, str, str, str] | None:
        doc = self._word_packs.document(word_pack_id).get()
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        rows = self._load_example_rows(word_pack_id)
        merged = merge_core_with_examples(str(data.get("data_core") or "{}"), rows)
        try:
            parsed = json.loads(merged) if merged else {}
        except Exception:
            parsed = {}
        parsed["checked_only_count"] = normalize_non_negative_int(
            data.get("checked_only_count")
        )
        parsed["learned_count"] = normalize_non_negative_int(data.get("learned_count"))
        with_progress = json.dumps(parsed, ensure_ascii=False)
        return (
            str(data.get("lemma_label") or ""),
            with_progress,
            str(data.get("created_at") or ""),
            str(data.get("updated_at") or ""),
        )

    def list_word_packs(
        self, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str]]:
        # Firestore 側で order_by + limit/offset を適用し、安定したページングを実現する。
        docs = self._fetch_word_pack_snapshots(limit, offset)
        items: list[tuple[str, str, str, str, str]] = []
        for doc in docs:
            data = doc.to_dict() or {}
            items.append(
                (
                    doc.id,
                    str(data.get("lemma_label") or ""),
                    str(data.get("sense_title") or ""),
                    str(data.get("created_at") or ""),
                    str(data.get("updated_at") or ""),
                )
            )
        return items

    def count_word_packs(self) -> int:
        query = self._ordered_word_pack_query()
        try:
            aggregation = query.count().get()
        except AttributeError as exc:  # pragma: no cover - defensive fallback
            msg = "Firestore client does not support aggregation queries"
            raise RuntimeError(msg) from exc
        return self._extract_count_from_aggregation(aggregation)

    def count_public_word_packs(self) -> int:
        """ゲスト公開フラグ付きの WordPack 件数を返す。"""

        query = self._ordered_word_pack_query().where("metadata.guest_public", "==", True)
        try:
            aggregation = query.count().get()
        except AttributeError as exc:  # pragma: no cover - defensive fallback
            msg = "Firestore client does not support aggregation queries"
            raise RuntimeError(msg) from exc
        return self._extract_count_from_aggregation(aggregation)

    def count_owned_word_packs(self, owner_user_id: str) -> int:
        """Return WordPack count visible to the owner-scoped strict mode."""

        query = self._ordered_word_pack_query().where("metadata.owner_user_id", "==", owner_user_id)
        try:
            aggregation = query.count().get()
        except AttributeError as exc:  # pragma: no cover - defensive fallback
            msg = "Firestore client does not support aggregation queries"
            raise RuntimeError(msg) from exc
        return self._extract_count_from_aggregation(aggregation)

    def has_guest_demo_word_pack(self) -> bool:
        """ゲスト閲覧用のデモデータが存在するかを軽量クエリで確認する。"""

        query = self._word_packs.where("metadata.guest_demo", "==", True).limit(1)
        for _ in query.stream():
            return True
        return False

    def list_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        docs = self._fetch_word_pack_snapshots(limit, offset)
        return [self._word_pack_list_item_with_flags(doc) for doc in docs]

    def list_all_word_packs_with_flags(
        self,
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        return [
            self._word_pack_list_item_with_flags(doc)
            for doc in self._ordered_word_pack_query().stream()
        ]

    def list_owned_word_packs_with_flags(
        self, owner_user_id: str, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        query = self._ordered_word_pack_query().where("metadata.owner_user_id", "==", owner_user_id)
        if offset:
            query = query.offset(max(0, int(offset)))
        query = query.limit(max(0, int(limit)))
        return [self._word_pack_list_item_with_flags(doc) for doc in query.stream()]

    def list_all_owned_word_packs_with_flags(
        self, owner_user_id: str
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        query = self._ordered_word_pack_query().where(
            "metadata.owner_user_id", "==", owner_user_id
        )
        return [self._word_pack_list_item_with_flags(doc) for doc in query.stream()]

    def _word_pack_list_item_with_flags(
        self, doc: firestore.DocumentSnapshot
    ) -> tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]:
        data = doc.to_dict() or {}
        counts_raw = data.get("examples_category_counts") or {}
        counts = {cat: int(counts_raw.get(cat, 0)) for cat in EXAMPLE_CATEGORIES}
        total = sum(counts.values())
        checked = normalize_non_negative_int(data.get("checked_only_count"))
        learned = normalize_non_negative_int(data.get("learned_count"))
        metadata = data.get("metadata") or {}
        guest_public = bool(metadata.get("guest_public", False)) if isinstance(metadata, Mapping) else False
        return (
            doc.id,
            str(data.get("lemma_label") or ""),
            str(data.get("sense_title") or ""),
            str(data.get("created_at") or ""),
            str(data.get("updated_at") or ""),
            total == 0,
            counts,
            checked,
            learned,
            guest_public,
        )

    def list_public_word_packs_with_flags(
        self, limit: int = 50, offset: int = 0
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        query = self._ordered_word_pack_query().where("metadata.guest_public", "==", True)
        if offset:
            query = query.offset(max(0, int(offset)))
        query = query.limit(max(0, int(limit)))
        return [self._word_pack_list_item_with_flags(doc) for doc in query.stream()]

    def list_all_public_word_packs_with_flags(
        self,
    ) -> list[tuple[str, str, str, str, str, bool, Mapping[str, int], int, int, bool]]:
        query = self._ordered_word_pack_query().where(
            "metadata.guest_public", "==", True
        )
        return [self._word_pack_list_item_with_flags(doc) for doc in query.stream()]

    def is_word_pack_guest_public(self, word_pack_id: str) -> bool:
        payload = self.get_word_pack_metadata(word_pack_id) or {}
        if not isinstance(payload, Mapping):
            return False
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, Mapping):
            return False
        return bool(metadata.get("guest_public", False))

    def delete_word_pack(self, word_pack_id: str) -> bool:
        doc_ref = self._word_packs.document(word_pack_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return False
        data = snapshot.to_dict() or {}
        existing_total, is_confident = self._extract_example_total(data)
        should_delete_examples = not is_confident or existing_total > 0
        if should_delete_examples:
            self._delete_examples(
                word_pack_id, expected_count=existing_total if is_confident else None
            )
        doc_ref.delete()
        return True

    def update_word_pack_study_progress(
        self, word_pack_id: str, checked_increment: int, learned_increment: int
    ) -> tuple[int, int] | None:
        doc_ref = self._word_packs.document(word_pack_id)
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
                    "updated_at": self._now_iso(),
                }
            )
        return next_checked, next_learned

    def find_word_pack_id_by_lemma(
        self, lemma: str, *, diagnostics: bool = False
    ) -> str | None | tuple[str | None, bool]:
        """大文字小文字を無視した lemma で WordPack ID を検索する。"""

        target = str(lemma or "").strip().lower()
        last_error: Exception | None = None

        for attempt in range(self._WORD_PACK_LOOKUP_RETRIES + 1):
            try:
                # lemma_label_lower の等価フィルタと更新日時降順の複合クエリで最新1件のみを取得し、全件走査を避ける。
                query = (
                    self._word_packs.where("lemma_label_lower", "==", target)
                    .order_by("updated_at", direction=firestore.Query.DESCENDING)
                    .limit(1)
                )
                for doc in query.stream():
                    return (doc.id, last_error is not None) if diagnostics else doc.id
                return (None, last_error is not None) if diagnostics else None
            except gexc.GoogleAPIError as exc:
                last_error = exc
                logger.warning(
                    "firestore_wordpack_lookup_retry",
                    lemma=target,
                    attempt=attempt + 1,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                )
                continue
            except Exception as exc:  # pragma: no cover - defensive guardrail
                last_error = exc
                logger.error(
                    "firestore_wordpack_lookup_error",
                    lemma=target,
                    attempt=attempt + 1,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                )
                break

        if last_error is not None:
            logger.error(
                "firestore_wordpack_lookup_give_up",
                lemma=target,
                attempts=self._WORD_PACK_LOOKUP_RETRIES + 1,
                error=str(last_error),
                error_class=last_error.__class__.__name__,
            )
        return (None, last_error is not None) if diagnostics else None

    def find_word_pack_by_lemma_ci(self, lemma: str) -> tuple[str, str, str] | None:
        target = str(lemma or "").strip().lower()
        # 最新の WordPack を 1 件だけ取得するため、Firestore 側の order_by + limit で走査量を抑える。
        query = (
            self._word_packs.where("lemma_label_lower", "==", target)
            .order_by("updated_at", direction=firestore.Query.DESCENDING)
            .limit(1)
        )
        for doc in query.stream():
            data = doc.to_dict() or {}
            return (
                doc.id,
                str(data.get("lemma_label") or ""),
                str(data.get("sense_title") or ""),
            )
        return None

    def reserve_example_ids(self, count: int) -> list[int]:
        return self._allocate_example_ids(count)

    def _delete_examples(self, word_pack_id: str, *, expected_count: int | None = None) -> None:
        """対象 WordPack の例文だけをページングしながら削除する。

        Firestore のバッチ上限（500件）に合わせて limit 付きクエリを繰り返し、
        1 回のコミットで触るドキュメント数を O(k) に抑える。expected_count が
        0 の場合はクエリ自体を発行しないことで無駄な読み出しを避ける。
        """

        if expected_count is not None and max(0, int(expected_count)) == 0:
            return

        batch_size = max(1, int(self._EXAMPLE_DELETE_BATCH_SIZE))
        base_query = (
            self._examples.where("word_pack_id", "==", word_pack_id)
            .order_by("__name__")
        )
        query = base_query.limit(batch_size)

        while True:
            snapshots = list(query.stream())
            if not snapshots:
                break

            batch = self._client.batch()
            for snapshot in snapshots:
                batch.delete(snapshot.reference)
            batch.commit()

            if len(snapshots) < batch_size:
                break
            query = base_query.start_after(snapshots[-1]).limit(batch_size)

    def _replace_examples(
        self,
        word_pack_id: str,
        *,
        lemma: str,
        sense_title: str,
        examples: Mapping[str, Any] | None,
        updated_at: str,
        existing_example_total: int | None = None,
        is_total_confident: bool = False,
        owner_user_id: str | None = None,
    ) -> dict[str, int]:
        # 例文数が 0 だと確実に分かっている場合のみ削除クエリを省略し、それ以外では安全側に倒す。
        should_delete_existing = not is_total_confident or existing_example_total not in (None, 0)
        if should_delete_existing:
            self._delete_examples(
                word_pack_id,
                expected_count=existing_example_total if is_total_confident else None,
            )
        counts = {cat: 0 for cat in EXAMPLE_CATEGORIES}
        if not isinstance(examples, Mapping):
            return counts
        rows = list(iter_example_rows(examples))
        ids = self._allocate_example_ids(len(rows))
        id_iter = iter(ids)
        for (
            category,
            position,
            en,
            ja,
            grammar_ja,
            llm_model,
            llm_params,
            checked_only_count,
            learned_count,
            transcription_typing_count,
        ) in rows:
            doc_id = str(next(id_iter))
            self._examples.document(doc_id).set(
                {
                    "example_id": int(doc_id),
                    "word_pack_id": word_pack_id,
                    "category": category,
                    "position": position,
                    "en": en,
                    "ja": ja,
                    "grammar_ja": grammar_ja,
                    "llm_model": llm_model,
                    "llm_params": llm_params,
                    "checked_only_count": normalize_non_negative_int(checked_only_count),
                    "learned_count": normalize_non_negative_int(learned_count),
                    "transcription_typing_count": normalize_non_negative_int(
                        transcription_typing_count
                    ),
                    "created_at": updated_at,
                    "pack_updated_at": updated_at,
                    "lemma": lemma,
                    "sense_title": sense_title,
                    "owner_user_id": owner_user_id,
                    **self._build_search_payload(en),
                }
            )
            counts[category] = counts.get(category, 0) + 1
        return counts

    def _load_example_rows(self, word_pack_id: str) -> Sequence[Mapping[str, Any]]:
        rows: list[Mapping[str, Any]] = []
        # FirestoreExampleRepository の検索条件と同一になるよう、ここでも word_pack_id の等価フィルタを明示する。
        query = self._examples.where("word_pack_id", "==", word_pack_id)
        for snapshot in query.stream():
            data = snapshot.to_dict() or {}
            rows.append(
                {
                    "category": data.get("category"),
                    "en": data.get("en"),
                    "ja": data.get("ja"),
                    "grammar_ja": data.get("grammar_ja"),
                    "llm_model": data.get("llm_model"),
                    "llm_params": data.get("llm_params"),
                    "checked_only_count": data.get("checked_only_count"),
                    "learned_count": data.get("learned_count"),
                    "transcription_typing_count": data.get("transcription_typing_count"),
                    "position": data.get("position", 0),
                }
            )
        rows.sort(
            key=lambda r: (
                str(r.get("category") or ""),
                int(r.get("position") or 0),
            )
        )
        return rows

    def _allocate_example_ids(self, count: int) -> list[int]:
        if count <= 0:
            return []
        counter_ref = self._metadata.document("example_counters")

        def _allocate_without_transaction() -> list[int]:
            snapshot = counter_ref.get()
            current = int((snapshot.to_dict() or {}).get("next_id", 1))
            ids = list(range(current, current + count))
            counter_ref.set({"next_id": current + count}, merge=True)
            return ids

        try:
            transaction = self._client.transaction()
        except AttributeError:  # pragma: no cover - defensive fallback
            transaction = None
        except Exception as exc:  # pragma: no cover - best-effort guard
            logger.warning(
                "firestore_allocate_ids_transaction_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                stage="init",
            )
            transaction = None

        if transaction is None:
            return _allocate_without_transaction()

        try:
            transaction._begin()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(
                "firestore_allocate_ids_transaction_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                stage="begin",
            )
            return _allocate_without_transaction()

        try:
            snapshot = self._coerce_firestore_snapshot(transaction.get(counter_ref))
            current_payload = (snapshot.to_dict() if snapshot is not None else {}) or {}
            current = int(current_payload.get("next_id", 1))
            ids = list(range(current, current + count))
            transaction.set(counter_ref, {"next_id": current + count}, merge=True)
            transaction._commit()
            return ids
        except (ValueError, gexc.GoogleAPIError) as exc:
            try:
                transaction._rollback()
            except Exception:  # pragma: no cover - rollback best-effort
                pass
            logger.warning(
                "firestore_allocate_ids_transaction_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                stage="body",
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            try:
                transaction._rollback()
            except Exception:  # pragma: no cover - rollback best-effort
                pass
            logger.warning(
                "firestore_allocate_ids_transaction_failed",
                error=str(exc),
                error_class=exc.__class__.__name__,
                stage="body",
            )
        return _allocate_without_transaction()

    def update_word_pack_metadata(
        self,
        word_pack_id: str,
        *,
        updated_at: str | None = None,
        category_counts: Mapping[str, int] | None = None,
        guest_public: bool | None = None,
    ) -> None:
        updates: dict[str, Any] = {}
        if updated_at is not None:
            updates["updated_at"] = updated_at
        if category_counts is not None:
            normalized = {cat: int(category_counts.get(cat, 0)) for cat in EXAMPLE_CATEGORIES}
            updates["examples_category_counts"] = normalized
        if guest_public is not None:
            updates["metadata.guest_public"] = bool(guest_public)
        if updates:
            self._word_packs.document(word_pack_id).update(updates)

    def get_word_pack_metadata(self, word_pack_id: str) -> Mapping[str, Any] | None:
        snapshot = self._word_packs.document(word_pack_id).get()
        if not snapshot.exists:
            return None
        return snapshot.to_dict() or {}

    def get_word_pack_visibility(self, word_pack_id: str) -> Mapping[str, Any] | None:
        payload = self.get_word_pack_metadata(word_pack_id)
        if not isinstance(payload, Mapping):
            return None
        metadata = payload.get("metadata") or {}
        owner_user_id = None
        guest_public = False
        if isinstance(metadata, Mapping):
            owner_raw = metadata.get("owner_user_id")
            owner_user_id = str(owner_raw).strip() if owner_raw else None
            guest_public = bool(metadata.get("guest_public", False))
        return {
            "guest_public": guest_public,
            "owner_user_id": owner_user_id,
        }

    def _upsert_lemma(
        self,
        *,
        label: str,
        sense_title: str,
        llm_model: str | None,
        llm_params: str | None,
        now: str,
    ) -> str:
        """正規化済みの lemma を単一ドキュメントへ upsert する。

        - 正規化ラベル（小文字化）を Firestore ドキュメントIDとして優先採用し、
          lookup を O(1) 化する。
        - 既存データ（旧ID形式）は normalized_label インデックスを用いた単一件
          クエリで探し、互換性を維持する。
        - create + exists チェックで同時書き込みによる重複作成を防ぎ、
          競合時は既存ドキュメントを再利用する。
        """
        original_label = str(label or "").strip()
        if not original_label:
            raise ValueError("lemma label must not be empty")
        normalized = original_label.lower()
        normalized_ref = self._lemmas.document(normalized)
        normalized_snapshot = normalized_ref.get()

        def _update_existing(snapshot: firestore.DocumentSnapshot) -> str:
            data = snapshot.to_dict() or {}
            stored_label = str(data.get("label") or "")
            new_label = (
                stored_label
                if stored_label.lower() == original_label.lower()
                else original_label
            )
            stripped_sense = str(sense_title or "").strip()
            stored_sense = str(data.get("sense_title") or "")
            new_sense = stored_sense or stripped_sense
            new_llm_model = llm_model if llm_model is not None else data.get("llm_model")
            new_llm_params = llm_params if llm_params is not None else data.get("llm_params")
            # normalized_label を確実に維持するため merge で更新する
            snapshot.reference.set(
                {
                    "label": new_label,
                    "normalized_label": normalized,
                    "sense_title": new_sense,
                    "llm_model": new_llm_model,
                    "llm_params": new_llm_params,
                },
                merge=True,
            )
            return snapshot.id

        if normalized_snapshot.exists:
            return _update_existing(normalized_snapshot)

        existing_snapshot = next(
            iter(
                self._lemmas.where("normalized_label", "==", normalized)
                .limit(1)
                .stream()
            ),
            None,
        )
        if existing_snapshot is not None:
            return _update_existing(existing_snapshot)

        payload = {
            "label": original_label,
            "normalized_label": normalized,
            "sense_title": sense_title or "",
            "llm_model": llm_model,
            "llm_params": llm_params,
            "created_at": now,
        }
        try:
            transaction = self._client.transaction()
        except AttributeError:  # pragma: no cover - defensive fallback
            transaction = None
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.warning(
                "firestore_upsert_lemma_transaction_failed",
                label=original_label,
                normalized_label=normalized,
                error=str(exc),
                error_class=exc.__class__.__name__,
                stage="init",
            )
            transaction = None

        if transaction is not None:
            try:
                transaction._begin()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.warning(
                    "firestore_upsert_lemma_transaction_failed",
                    label=original_label,
                    normalized_label=normalized,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                    stage="begin",
                )
                transaction = None

        if transaction is not None:
            try:
                with self._lemma_write_lock:
                    snapshot = self._coerce_firestore_snapshot(transaction.get(normalized_ref))
                    if snapshot is not None and snapshot.exists:
                        transaction._rollback()
                        return _update_existing(snapshot)
                    try:
                        transaction.create(normalized_ref, payload)
                    except AlreadyExists:
                        transaction._rollback()
                        existing = normalized_ref.get()
                        if existing.exists:
                            return _update_existing(existing)
                transaction._commit()
                return normalized_ref.id
            except (ValueError, gexc.GoogleAPIError) as exc:
                try:
                    transaction._rollback()
                except Exception:  # pragma: no cover - rollback best-effort
                    pass
                logger.warning(
                    "firestore_upsert_lemma_transaction_failed",
                    label=original_label,
                    normalized_label=normalized,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                    stage="body",
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                try:
                    transaction._rollback()
                except Exception:  # pragma: no cover - rollback best-effort
                    pass
                logger.warning(
                    "firestore_upsert_lemma_transaction_failed",
                    label=original_label,
                    normalized_label=normalized,
                    error=str(exc),
                    error_class=exc.__class__.__name__,
                    stage="body",
                )

        try:
            normalized_ref.create(payload)
            return normalized_ref.id
        except AlreadyExists:
            fallback_snapshot = normalized_ref.get()
            if fallback_snapshot.exists:
                return _update_existing(fallback_snapshot)
            legacy_snapshot = next(
                iter(
                    self._lemmas.where("normalized_label", "==", normalized)
                    .limit(1)
                    .stream()
                ),
                None,
            )
            if legacy_snapshot is not None:
                return _update_existing(legacy_snapshot)
            # create が競合し、かつ再取得でも無い場合は新IDで再生成しておく
            lemma_id = f"lm:{normalized}:{uuid.uuid4().hex[:8]}"
            self._lemmas.document(lemma_id).set(payload)
            return lemma_id


FirestoreWordPackStore = FirestoreWordPackRepository

__all__ = ["FirestoreWordPackRepository", "FirestoreWordPackStore"]
