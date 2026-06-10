"""Bot-scoped pgvector storage for book chunks."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters, VectorStoreQuery
from llama_index.vector_stores.postgres import PGVectorStore
from sqlalchemy import text as sql_text
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from memory.llamaindex.vector_store import _to_async_db_url

logger = logging.getLogger(__name__)


class BookVectorStore:
    """PGVector-backed store for immutable, bot-scoped book chunks."""

    def __init__(self, db_url: str, table_name: str, embed_dim: int):
        url = make_url(db_url)
        self._store = PGVectorStore.from_params(
            host=url.host,
            port=str(url.port),
            database=url.database,
            user=url.username,
            password=url.password,
            table_name=table_name,
            embed_dim=embed_dim,
        )
        self._engine: AsyncEngine = create_async_engine(_to_async_db_url(db_url))

    async def upsert(self, nodes: list[Any]) -> None:
        """Upsert book chunk nodes."""
        if not nodes:
            return
        await asyncio.to_thread(self._store.add, nodes)

    async def query(
        self,
        query_embedding: list[float],
        top_k: int,
        bot_id: str,
        min_score: float | None = None,
    ) -> list[NodeWithScore]:
        """Query book chunks scoped to one bot."""
        filters = MetadataFilters(
            filters=[ExactMatchFilter(key="bot_id", value=str(bot_id))]
        )
        query_obj = VectorStoreQuery(
            query_embedding=query_embedding,
            similarity_top_k=top_k,
            filters=filters,
        )
        result = await asyncio.to_thread(self._store.query, query_obj)

        nodes_with_scores: list[NodeWithScore] = []
        similarities = result.similarities or []
        for index, node in enumerate(result.nodes):
            score = similarities[index] if index < len(similarities) else None
            if min_score is not None and (score is None or score < min_score):
                continue
            nodes_with_scores.append(NodeWithScore(node=node, score=score))
        return nodes_with_scores

    async def delete_book(self, book_id: str) -> None:
        """Delete all vector rows for a book."""
        table_name = self._store.table_name
        sql = (
            f'DELETE FROM public."data_{table_name}" '
            f"WHERE metadata_->>'book_id' = :bid"
        )
        async with self._engine.begin() as conn:
            await conn.execute(sql_text(sql), {"bid": str(book_id)})
        logger.info("Deleted book vector chunks for book %s", book_id)

    async def fetch_neighbors(
        self,
        book_id: str,
        chunk_index: int,
        radius: int = 1,
    ) -> list[dict]:
        """Fetch neighboring chunks from the same book."""
        table_name = self._store.table_name
        sql = (
            f'SELECT text, metadata_ FROM public."data_{table_name}" '
            f"WHERE metadata_->>'book_id' = :bid "
            f"AND CAST(metadata_->>'chunk_index' AS INTEGER) "
            f"BETWEEN :min_idx AND :max_idx "
            f"ORDER BY CAST(metadata_->>'chunk_index' AS INTEGER)"
        )
        async with self._engine.connect() as conn:
            result = await conn.execute(
                sql_text(sql),
                {
                    "bid": str(book_id),
                    "min_idx": max(0, chunk_index - radius),
                    "max_idx": chunk_index + radius,
                },
            )
            rows = []
            for row in result.mappings():
                metadata = row.get("metadata_", {})
                if not isinstance(metadata, dict):
                    metadata = {}
                rows.append(
                    {
                        "text": row.get("text", ""),
                        "book_id": metadata.get("book_id", str(book_id)),
                        "book_title": metadata.get("book_title", ""),
                        "author": metadata.get("author", ""),
                        "chunk_index": metadata.get("chunk_index"),
                    }
                )
            return rows
