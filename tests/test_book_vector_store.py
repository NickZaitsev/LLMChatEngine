from __future__ import annotations

import pytest

from knowledge.store import BookVectorStore


class _FakePgStore:
    table_name = "book_chunks"

    def __init__(self) -> None:
        self.initialized = False

    def _initialize(self) -> None:
        self.initialized = True


class _FakeConnection:
    def __init__(self, store: _FakePgStore) -> None:
        self.store = store
        self.executed = False

    async def execute(self, statement, parameters):
        if not self.store.initialized:
            raise RuntimeError("vector table has not been initialized")
        self.executed = True


class _FakeTransaction:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _FakeEngine:
    def __init__(self, store: _FakePgStore) -> None:
        self.connection = _FakeConnection(store)

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self.connection)


@pytest.mark.asyncio
async def test_delete_book_initializes_vector_table_before_direct_sql() -> None:
    pg_store = _FakePgStore()
    engine = _FakeEngine(pg_store)
    store = BookVectorStore.__new__(BookVectorStore)
    store._store = pg_store
    store._engine = engine
    store._closed = False

    await store.delete_book("book-1")

    assert pg_store.initialized is True
    assert engine.connection.executed is True
