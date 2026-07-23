import pytest
from llama_index.core.schema import TextNode

from knowledge.chunker import BookChunk
from knowledge.manager import BookKnowledgeManager


class FakeEmbeddingModel:
    def __init__(self):
        self.single_queries = []
        self.batch_texts = []

    async def get_embedding(self, text):
        self.single_queries.append(text)
        return [float(len(text))]

    async def get_embeddings(self, texts):
        self.batch_texts.append(list(texts))
        return [[float(index + 1)] for index, _ in enumerate(texts)]


class FakeBookStore:
    def __init__(self, query_nodes=None, neighbors=None):
        self.deleted_books = []
        self.upsert_batches = []
        self.query_calls = []
        self.query_nodes = query_nodes or []
        self.neighbors = neighbors or {}

    async def delete_book(self, book_id):
        self.deleted_books.append(book_id)

    async def upsert(self, nodes):
        self.upsert_batches.append(list(nodes))

    async def query(self, query_embedding, top_k, bot_id, min_score=None):
        self.query_calls.append(
            {
                "query_embedding": query_embedding,
                "top_k": top_k,
                "bot_id": bot_id,
                "min_score": min_score,
            }
        )
        return self.query_nodes

    async def fetch_neighbors(self, book_id, chunk_index, radius):
        return self.neighbors.get((book_id, chunk_index, radius), [])


@pytest.mark.asyncio
async def test_ingest_book_deletes_old_chunks_and_batches_embeddings(monkeypatch):
    chunks = [
        BookChunk(text="chunk one", chunk_index=0),
        BookChunk(text="chunk two", chunk_index=1),
        BookChunk(text="chunk three", chunk_index=2),
    ]
    monkeypatch.setattr("knowledge.manager.chunk_text", lambda text: chunks)
    store = FakeBookStore()
    embeddings = FakeEmbeddingModel()
    manager = BookKnowledgeManager(store, embeddings, embed_batch_size=2)

    count = await manager.ingest_book(
        book_id="book-1",
        bot_id="bot-1",
        title="The Book",
        author="The Author",
        text="ignored by monkeypatch",
    )

    assert count == 3
    assert store.deleted_books == ["book-1"]
    assert embeddings.batch_texts == [["chunk one", "chunk two"], ["chunk three"]]
    assert len(store.upsert_batches) == 2
    first_node = store.upsert_batches[0][0]
    assert first_node.get_content() == "chunk one"
    assert first_node.embedding == [1.0]
    assert first_node.metadata == {
        "bot_id": "bot-1",
        "book_id": "book-1",
        "book_title": "The Book",
        "author": "The Author",
        "chunk_index": "0",
    }


@pytest.mark.asyncio
async def test_ingest_book_returns_zero_for_empty_chunks(monkeypatch):
    monkeypatch.setattr("knowledge.manager.chunk_text", lambda text: [])
    store = FakeBookStore()
    manager = BookKnowledgeManager(store, FakeEmbeddingModel())

    count = await manager.ingest_book("book-1", "bot-1", "Title", "Author", "")

    assert count == 0
    assert store.deleted_books == ["book-1"]
    assert store.upsert_batches == []


@pytest.mark.asyncio
async def test_get_context_queries_store_and_formats_ordered_chunks():
    nodes = [
        TextNode(
            text="Later chunk",
            metadata={
                "bot_id": "bot-1",
                "book_id": "book-b",
                "book_title": "Book B",
                "author": "Author",
                "chunk_index": "2",
            },
        ),
        TextNode(
            text="Earlier chunk",
            metadata={
                "bot_id": "bot-1",
                "book_id": "book-a",
                "book_title": "Book A",
                "author": "Author",
                "chunk_index": "1",
            },
        ),
    ]
    store = FakeBookStore(query_nodes=nodes)
    embeddings = FakeEmbeddingModel()
    manager = BookKnowledgeManager(store, embeddings, expand_neighbors=0)

    context = await manager.get_context(
        bot_id="bot-1",
        query="what matters?",
        top_k=4,
        min_score=0.35,
    )

    assert embeddings.single_queries == ["what matters?"]
    assert store.query_calls == [
        {
            "query_embedding": [13.0],
            "top_k": 4,
            "bot_id": "bot-1",
            "min_score": 0.35,
        }
    ]
    assert context == "[«Book A»]\nEarlier chunk\n---\n[«Book B»]\nLater chunk"


@pytest.mark.asyncio
async def test_get_context_expands_neighbors_and_deduplicates():
    node = TextNode(
        text="Matched chunk",
        metadata={
            "book_id": "book-1",
            "book_title": "Book",
            "author": "Author",
            "chunk_index": "1",
        },
    )
    neighbors = {
        ("book-1", 1, 1): [
            {
                "text": "Previous chunk",
                "book_id": "book-1",
                "book_title": "Book",
                "author": "Author",
                "chunk_index": "0",
            },
            {
                "text": "Matched chunk",
                "book_id": "book-1",
                "book_title": "Book",
                "author": "Author",
                "chunk_index": "1",
            },
            {
                "text": "Matched chunk duplicate",
                "book_id": "book-1",
                "book_title": "Book",
                "author": "Author",
                "chunk_index": "1",
            },
        ]
    }
    store = FakeBookStore(query_nodes=[node], neighbors=neighbors)
    manager = BookKnowledgeManager(store, FakeEmbeddingModel(), expand_neighbors=1)

    context = await manager.get_context("bot-1", "query", top_k=1)

    assert context == "[«Book»]\nPrevious chunk\n---\n[«Book»]\nMatched chunk"


@pytest.mark.asyncio
async def test_delete_book_delegates_to_store():
    store = FakeBookStore()
    manager = BookKnowledgeManager(store, FakeEmbeddingModel())

    await manager.delete_book("book-1")

    assert store.deleted_books == ["book-1"]
