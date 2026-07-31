"""Firestore をテストで再現するための簡易フェイク実装。"""

from __future__ import annotations

from typing import Any
import uuid

from google.api_core.exceptions import AlreadyExists
from google.cloud import firestore


class FakeDocumentSnapshot:
    def __init__(self, collection: str, doc_id: str, data: dict[str, Any] | None, client: "FakeFirestoreClient") -> None:
        self._collection = collection
        self.id = doc_id
        self._data = data
        self._client = client

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return None if self._data is None else dict(self._data)

    @property
    def reference(self) -> "FakeDocumentReference":
        return FakeDocumentReference(self._client, self._collection, self.id)


class FakeDocumentReference:
    def __init__(self, client: "FakeFirestoreClient", collection: str, doc_id: str) -> None:
        self._client = client
        self._collection = collection
        self.id = doc_id

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        bucket = self._client._data.setdefault(self._collection, {})
        if merge and self.id in bucket:
            bucket[self.id].update(data)
        else:
            bucket[self.id] = dict(data)

    def create(self, data: dict[str, Any]) -> None:
        bucket = self._client._data.setdefault(self._collection, {})
        if self.id in bucket:
            raise AlreadyExists(f"document {self._collection}/{self.id} already exists")
        bucket[self.id] = dict(data)

    def update(self, data: dict[str, Any]) -> None:
        bucket = self._client._data.setdefault(self._collection, {})
        if self.id not in bucket:
            raise KeyError(f"document {self._collection}/{self.id} not found")
        payload = bucket[self.id]
        for key, value in data.items():
            if "." not in key:
                payload[key] = value
                continue
            current: dict[str, Any] = payload
            parts = key.split(".")
            for part in parts[:-1]:
                nested = current.get(part)
                if not isinstance(nested, dict):
                    nested = {}
                    current[part] = nested
                current = nested
            current[parts[-1]] = value

    def get(self, transaction: "FakeTransaction" | None = None) -> FakeDocumentSnapshot:
        bucket = self._client._data.setdefault(self._collection, {})
        payload = dict(bucket[self.id]) if self.id in bucket else None
        return FakeDocumentSnapshot(self._collection, self.id, payload, self._client)

    def delete(self) -> None:
        bucket = self._client._data.setdefault(self._collection, {})
        bucket.pop(self.id, None)


class FakeCollectionReference:
    def __init__(self, client: "FakeFirestoreClient", name: str) -> None:
        self._client = client
        self._name = name
        self._count_calls = 0
        self._query_log: list[dict[str, Any]] = []

    def document(self, doc_id: str) -> FakeDocumentReference:
        return FakeDocumentReference(self._client, self._name, doc_id)

    def _all_snapshots(self) -> list[FakeDocumentSnapshot]:
        bucket = self._client._data.setdefault(self._name, {})
        return [
            FakeDocumentSnapshot(self._name, doc_id, dict(data), self._client)
            for doc_id, data in bucket.items()
        ]

    def stream(self):  # pragma: no cover - simple iterator
        docs = self._all_snapshots()
        self._record_query([], len(docs))
        for snapshot in docs:
            yield snapshot

    def order_by(self, field_path: str, direction=firestore.Query.ASCENDING):
        return FakeQuery(self).order_by(field_path, direction)

    def where(self, field_path: str, op_string: str, value: Any):
        return FakeQuery(self).where(field_path, op_string, value)

    def count(self, alias: str | None = None) -> "FakeAggregationQuery":
        self._count_calls += 1
        return FakeAggregationQuery(FakeQuery(self), alias or "count")

    @property
    def count_calls(self) -> int:
        return self._count_calls

    def _record_query(
        self, filters: list[tuple[str, str, Any]], size: int, limit: int | None = None
    ) -> None:  # pragma: no cover - bookkeeping helper
        self._query_log.append({"filters": list(filters), "size": size, "limit": limit})

    def reset_query_log(self) -> None:
        self._query_log.clear()

    @property
    def query_log(self) -> list[dict[str, Any]]:
        return list(self._query_log)


class FakeQuery:
    def __init__(
        self,
        collection: FakeCollectionReference,
        *,
        orderings: list[tuple[str, bool]] | None = None,
        filters: list[tuple[str, str, Any]] | None = None,
        limit: int | None = None,
        offset: int = 0,
        start_after_id: str | None = None,
    ) -> None:
        self._collection = collection
        self._orderings: list[tuple[str, bool]] = list(orderings or [])
        self._filters: list[tuple[str, str, Any]] = list(filters or [])
        self._limit: int | None = limit
        self._offset = offset
        self._start_after_id = start_after_id

    def _clone(self, **kwargs: Any) -> "FakeQuery":
        """Return a shallow copy with updated attributes."""

        params = {
            "collection": self._collection,
            "orderings": kwargs.pop("orderings", self._orderings),
            "filters": kwargs.pop("filters", self._filters),
            "limit": kwargs.pop("limit", self._limit),
            "offset": kwargs.pop("offset", self._offset),
            "start_after_id": kwargs.pop("start_after_id", self._start_after_id),
        }
        params.update(kwargs)
        return FakeQuery(**params)

    def order_by(self, field_path: str, direction=firestore.Query.ASCENDING) -> "FakeQuery":
        updated = list(self._orderings)
        updated.append((field_path, direction == firestore.Query.DESCENDING))
        return self._clone(orderings=updated)

    def where(self, field_path: str, op_string: str, value: Any) -> "FakeQuery":
        updated = list(self._filters)
        updated.append((field_path, op_string, value))
        return self._clone(filters=updated)

    def limit(self, value: int) -> "FakeQuery":
        return self._clone(limit=max(0, int(value)))

    def offset(self, value: int) -> "FakeQuery":
        return self._clone(offset=max(0, int(value)))

    def start_after(self, snapshot: FakeDocumentSnapshot) -> "FakeQuery":
        return self._clone(start_after_id=snapshot.id)

    def _matching_snapshots(self) -> list[FakeDocumentSnapshot]:
        docs = self._collection._all_snapshots()
        for field_path, op_string, expected in self._filters:
            docs = [
                doc
                for doc in docs
                if self._matches_filter(doc, field_path, op_string, expected)
            ]
        for field_path, descending in reversed(self._orderings):
            docs.sort(
                key=lambda snap, fp=field_path: self._order_value(snap, fp),
                reverse=descending,
            )
        if self._start_after_id:
            ids = [snap.id for snap in docs]
            if self._start_after_id in ids:
                start_index = ids.index(self._start_after_id) + 1
                docs = docs[start_index:]
        if self._offset:
            docs = docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        return docs

    def stream(self):  # pragma: no cover - passthrough iterator
        results = self._matching_snapshots()
        self._collection._record_query(self._filters, len(results), self._limit)
        for snapshot in results:
            yield snapshot

    def count(self, alias: str | None = None) -> "FakeAggregationQuery":
        self._collection._count_calls += 1
        return FakeAggregationQuery(self, alias or "count")

    def _matches_filter(
        self,
        snapshot: FakeDocumentSnapshot,
        field_path: str,
        op_string: str,
        expected: Any,
    ) -> bool:
        data = snapshot.to_dict() or {}
        actual = self._resolve_field_path(data, field_path)
        if op_string == "==":
            return actual == expected
        if op_string == "array_contains":
            try:
                return expected in (actual or [])
            except TypeError:
                return False
        if op_string == ">=":
            return actual >= expected
        if op_string == "<=":
            return actual <= expected
        if op_string == ">":
            return actual > expected
        if op_string == "<":
            return actual < expected
        raise NotImplementedError(f"unsupported operator: {op_string}")

    def _resolve_field_path(self, data: dict[str, Any], field_path: str) -> Any:
        """Firestore のドット区切り field_path を dict から辿る。"""

        if "." not in field_path:
            return data.get(field_path)
        current: Any = data
        for key in field_path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _order_value(self, snapshot: FakeDocumentSnapshot, field_path: str) -> Any:
        data = snapshot.to_dict() or {}
        if field_path == "__name__":
            return snapshot.id
        value = data.get(field_path)
        if isinstance(value, (int, float)):
            return value
        return str(value or "")


class FakeAggregationQuery:
    def __init__(self, query: FakeQuery, alias: str) -> None:
        self._query = query
        self._alias = alias

    def stream(self, *args: Any, **kwargs: Any):  # pragma: no cover - simple iterator
        total = len(self._query._matching_snapshots())
        yield FakeAggregationResult(self._alias, total)

    def get(self, *args: Any, **kwargs: Any) -> list["FakeAggregationResult"]:
        return list(self.stream(*args, **kwargs))


class FakeAggregationResult:
    def __init__(self, alias: str, value: int) -> None:
        self.alias = alias
        self.value = value
        self.aggregate_fields = {alias: value}

    def __getitem__(self, key: str) -> int:
        return self.aggregate_fields[key]


_TRANSACTION_NOT_IN_PROGRESS = "Transaction not in progress, cannot be used in API requests."


class FakeTransaction:
    def __init__(self, client: "FakeFirestoreClient") -> None:
        self._client = client
        self._in_progress = False
        self._id: str | None = None

    @property
    def in_progress(self) -> bool:
        return self._in_progress

    @property
    def id(self) -> str | None:
        return self._id

    def __enter__(self) -> "FakeTransaction":  # pragma: no cover - helper
        self._begin()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # pragma: no cover - helper
        try:
            if exc_type is None:
                self._commit()
            else:
                self._rollback()
        except ValueError:
            pass

    def _clean_up(self) -> None:
        self._in_progress = False
        self._id = None

    def _begin(self) -> None:
        if self._in_progress:
            raise ValueError("Transaction already in progress.")
        self._in_progress = True
        self._id = f"fake-txn-{uuid.uuid4().hex}"

    def _rollback(self) -> None:
        if not self._in_progress:
            raise ValueError(_TRANSACTION_NOT_IN_PROGRESS)
        self._clean_up()

    def _commit(self) -> None:
        if not self._in_progress:
            raise ValueError(_TRANSACTION_NOT_IN_PROGRESS)
        self._clean_up()

    def _ensure_active(self) -> None:
        if not self._in_progress:
            raise ValueError(_TRANSACTION_NOT_IN_PROGRESS)

    def get(self, doc_ref: FakeDocumentReference) -> FakeDocumentSnapshot:
        self._ensure_active()
        return doc_ref.get()

    def create(self, doc_ref: FakeDocumentReference, data: dict[str, Any]) -> None:
        self._ensure_active()
        doc_ref.create(data)

    def set(self, doc_ref: FakeDocumentReference, data: dict[str, Any], merge: bool = False) -> None:
        self._ensure_active()
        doc_ref.set(data, merge=merge)

    def update(self, doc_ref: FakeDocumentReference, data: dict[str, Any]) -> None:
        self._ensure_active()
        doc_ref.update(data)


class FakeWriteBatch:
    """Firestore の WriteBatch API を模した簡易フェイク。"""

    def __init__(self, client: "FakeFirestoreClient") -> None:
        self._client = client
        self._operations: list[tuple[str, Any]] = []

    def delete(self, doc_ref: FakeDocumentReference) -> None:
        self._operations.append(("delete", doc_ref))

    def set(self, doc_ref: FakeDocumentReference, data: dict[str, Any]) -> None:
        self._operations.append(("set", (doc_ref, data)))

    def update(self, doc_ref: FakeDocumentReference, data: dict[str, Any]) -> None:
        self._operations.append(("update", (doc_ref, data)))

    def commit(self) -> None:
        for action, payload in list(self._operations):
            if action == "delete":
                ref: FakeDocumentReference = payload  # type: ignore[assignment]
                ref.delete()
            elif action == "set":
                ref, data = payload  # type: ignore[misc]
                ref.set(data)
            elif action == "update":
                ref, data = payload  # type: ignore[misc]
                ref.update(data)


def ensure_firestore_test_env(monkeypatch) -> None:
    """テスト用に Firestore 接続先をエミュレータ/フェイクへ固定する環境変数を設定する。

    なぜ: backend.store._create_store は環境変数を参照して Firestore クライアントを初期化するため、
    ここで事前に値を上書きしておくとストア生成が実際の GCP へ向かう誤配を防げる。
    """

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "localhost:8080")
    monkeypatch.setenv("FIRESTORE_PROJECT_ID", "test-project")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")


def use_fake_firestore_client(monkeypatch, client: "FakeFirestoreClient | None" = None) -> "FakeFirestoreClient":
    """google.cloud.firestore.Client をフェイクに差し替え、同一インスタンスを返す。

    返却したフェイククライアントは永続層の状態を保持するため、同一テスト内で何度も
    import/reload を行ってもデータが失われないようにする。
    """

    instance = client or FakeFirestoreClient()
    monkeypatch.setattr(firestore, "Client", lambda *args, **kwargs: instance)
    return instance


class FakeFirestoreClient:
    """google.cloud.firestore.Client 互換の最小フェイク。

    - collection/transaction/batch だけを実装し、AppFirestoreStore が依存する CRUD/ページング/検索を網羅する。
    - _data は collection ごとに {doc_id: payload} を保持し、テスト毎に新規インスタンスで分離する。
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict[str, Any]]] = {}

    def collection(self, name: str) -> FakeCollectionReference:
        return FakeCollectionReference(self, name)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    def batch(self) -> FakeWriteBatch:
        return FakeWriteBatch(self)
