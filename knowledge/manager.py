"""Book knowledge ingestion and retrieval orchestration."""

from __future__ import annotations

import logging
from typing import Any, Iterable

from llama_index.core.schema import TextNode

from core.abstractions import EmbeddingModel, KnowledgeStore
from knowledge.chunker import chunk_text
from settings import settings

BOOK_EMBED_BATCH_SIZE = settings.books.embed_batch_size
BOOK_RAG_EXPAND_NEIGHBORS = settings.books.rag_expand_neighbors

logger = logging.getLogger(__name__)


class BookKnowledgeManager:
    """Coordinates book chunking, embedding, storage, and retrieval."""

    def __init__(
        self,
        store: KnowledgeStore,
        embedding_model: EmbeddingModel,
        expand_neighbors: int = BOOK_RAG_EXPAND_NEIGHBORS,
        embed_batch_size: int = BOOK_EMBED_BATCH_SIZE,
    ):
        self._store = store
        self._embedding_model = embedding_model
        self._expand_neighbors = expand_neighbors
        self._embed_batch_size = embed_batch_size

    async def ingest_book(
        self,
        book_id: str,
        bot_id: str,
        title: str,
        author: str,
        text: str,
    ) -> int:
        """Chunk, embed, and store one book. Safe to retry."""
        await self._store.delete_book(str(book_id))
        chunks = chunk_text(text)
        if not chunks:
            return 0

        stored_count = 0
        for batch in _batches(chunks, self._embed_batch_size):
            texts = [chunk.text for chunk in batch]
            embeddings = await self._embedding_model.get_embeddings(texts)
            nodes: list[TextNode] = []
            for chunk, embedding in zip(batch, embeddings):
                if not embedding:
                    logger.warning(
                        "Empty embedding for book %s chunk %d; skipping",
                        book_id,
                        chunk.chunk_index,
                    )
                    continue
                nodes.append(
                    TextNode(
                        text=chunk.text,
                        embedding=embedding,
                        metadata={
                            "bot_id": str(bot_id),
                            "book_id": str(book_id),
                            "book_title": title,
                            "author": author,
                            "chunk_index": str(chunk.chunk_index),
                        },
                    )
                )

            if nodes:
                await self._store.upsert(nodes)
                stored_count += len(nodes)

        logger.info("Stored %d chunk(s) for book %s", stored_count, book_id)
        return stored_count

    async def get_context(
        self,
        bot_id: str,
        query: str,
        top_k: int,
        min_score: float | None = None,
    ) -> str:
        """Retrieve and format book context for a bot."""
        query_embedding = await self._embedding_model.get_embedding(query)
        if not query_embedding:
            return ""

        nodes = await self._store.query(
            query_embedding=query_embedding,
            top_k=top_k,
            bot_id=str(bot_id),
            min_score=min_score,
        )
        if not nodes:
            return ""

        chunks = await self._expand_and_order(nodes)
        return "\n---\n".join(
            f"[«{chunk['book_title']}»]\n{chunk['text']}" for chunk in chunks
        )

    async def delete_book(self, book_id: str) -> None:
        """Delete vector chunks for a book."""
        await self._store.delete_book(str(book_id))

    async def _expand_and_order(self, nodes: list[Any]) -> list[dict]:
        seen: set[tuple[str, int | None]] = set()
        chunks: list[dict] = []

        for node_with_score in nodes:
            node = getattr(node_with_score, "node", node_with_score)
            metadata = getattr(node, "metadata", {}) or {}
            book_id = metadata.get("book_id")
            chunk_index = _parse_chunk_index(metadata.get("chunk_index"))

            if (
                self._expand_neighbors > 0
                and book_id
                and chunk_index is not None
                and hasattr(self._store, "fetch_neighbors")
            ):
                neighbors = await self._store.fetch_neighbors(
                    book_id=str(book_id),
                    chunk_index=chunk_index,
                    radius=self._expand_neighbors,
                )
                for neighbor in neighbors:
                    self._append_chunk(chunks, seen, neighbor)
                continue

            self._append_chunk(
                chunks,
                seen,
                {
                    "text": node.get_content(),
                    "book_id": book_id or "",
                    "book_title": metadata.get("book_title", ""),
                    "author": metadata.get("author", ""),
                    "chunk_index": chunk_index,
                },
            )

        chunks.sort(key=lambda item: (str(item["book_id"]), item["chunk_index"] or 0))
        return chunks

    @staticmethod
    def _append_chunk(
        chunks: list[dict],
        seen: set[tuple[str, int | None]],
        chunk: dict,
    ) -> None:
        text = chunk.get("text", "")
        if not text:
            return
        key = (str(chunk.get("book_id", "")), _parse_chunk_index(chunk.get("chunk_index")))
        if key in seen:
            return
        seen.add(key)
        chunks.append(
            {
                "text": text,
                "book_id": str(chunk.get("book_id", "")),
                "book_title": str(chunk.get("book_title", "")),
                "author": str(chunk.get("author", "")),
                "chunk_index": key[1],
            }
        )


def _batches(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


def _parse_chunk_index(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
