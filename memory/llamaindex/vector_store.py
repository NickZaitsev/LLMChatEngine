"""
LlamaIndex PGVector store implementation.

This module provides the `PgVectorStore` class, which implements the
`VectorStore` abstraction for a PostgreSQL database with the pgvector
extension. It handles the connection to the database and provides methods
for upserting, querying, and clearing vector data.
"""

import asyncio
import logging
from typing import List, Any, Optional

from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.vector_stores import (
    VectorStoreQuery,
    MetadataFilters,
    ExactMatchFilter,
)
from sqlalchemy.engine.url import make_url
from sqlalchemy import text as sql_text

from core.abstractions import VectorStore as VectorStoreAbstraction

logger = logging.getLogger(__name__)


class PgVectorStore(VectorStoreAbstraction):
    """
    PGVectorStore implementation for LlamaIndex.
    """

    def __init__(self, db_url: str, table_name: str, embed_dim: int):
        """
        Initialize the PgVectorStore.

        Args:
            db_url: The PostgreSQL database URL.
            table_name: The name of the table to use for the vector store.
            embed_dim: The embedding dimension.
        """
        url = make_url(db_url)

        # PGVectorStore requires separate connection parameters, so we parse them from the URL
        self._store = PGVectorStore.from_params(
            host=url.host,
            port=str(url.port),
            database=url.database,
            user=url.username,
            password=url.password,
            table_name=table_name,
            embed_dim=embed_dim,
        )

    async def upsert(self, nodes: List[Any]) -> None:
        """
        Upsert nodes into the vector store.

        Args:
            nodes: A list of nodes to upsert.
        """
        await asyncio.to_thread(self._store.add, nodes)

    async def query(
        self, query_embedding: List[float], top_k: int, user_id: str, bot_id: Optional[str] = None
    ) -> List[Any]:
        """
        Query the vector store for similar nodes.

        Args:
            query_embedding: The query embedding.
            top_k: The number of top results to return.
            user_id: The ID of the user to filter memories for.
            bot_id: Optional ID of the bot to filter memories for.

        Returns:
            A list of similar nodes.
        """
        logger.info(
            f"==> PGVectorStore querying with user_id='{user_id}', bot_id='{bot_id}', top_k={top_k}"
        )
        try:
            filters_list = [ExactMatchFilter(key="user_id", value=str(user_id))]
            if bot_id:
                filters_list.append(ExactMatchFilter(key="bot_id", value=str(bot_id)))

            filters = MetadataFilters(filters=filters_list)
            logger.info(f"PGVectorStore query filters: {filters_list}")

            query_obj = VectorStoreQuery(
                query_embedding=query_embedding,
                similarity_top_k=top_k,
                filters=filters,
            )

            result = await asyncio.to_thread(self._store.query, query_obj)
            logger.info(f"<== PGVectorStore query returned {len(result.nodes)} nodes")
            
            for i, node in enumerate(result.nodes):
                score = result.similarities[i] if result.similarities and i < len(result.similarities) else "N/A"
                logger.debug(f"  Node {i+1} [Score: {score}]: {node.get_content()[:100]}... Metadata: {node.metadata}")
            
            return result.nodes
        except Exception as e:
            logger.error(f"Error in vector store query: {e}", exc_info=True)
            raise

    async def clear(self, user_id: str, bot_id: Optional[str] = None) -> None:
        """
        Clear all nodes for a specific user (and optionally bot) from the vector store.

        Args:
            user_id: The ID of the user whose data should be cleared.
            bot_id: Optional ID of the bot to filter clearing.
        """
        try:
            table_name = self._store.table_name

            # NOTE:
            # This assumes LlamaIndex created a table named public."data_{table_name}"
            # with JSON/JSONB column metadata_.
            # If your schema/table differs, adjust this SQL accordingly.
            def _delete():
                with self._store._session() as session:
                    sql = (
                        f'DELETE FROM public."data_{table_name}" '
                        f"WHERE metadata_->>'user_id' = :uid"
                    )
                    params = {"uid": str(user_id)}

                    if bot_id:
                        sql += " AND metadata_->>'bot_id' = :bid"
                        params["bid"] = str(bot_id)

                    session.execute(sql_text(sql), params)
                    session.commit()

            await asyncio.to_thread(_delete)
            logger.info(f"Cleared vector store entries for user {user_id} (bot_id={bot_id})")
        except Exception as e:
            logger.error(
                f"Failed to clear vector store for user {user_id} (bot_id={bot_id}): {e}",
                exc_info=True,
            )
            raise

    async def find_similar(
        self,
        query_embedding: List[float],
        user_id: str,
        threshold: float = 0.85,
        top_k: int = 3,
        bot_id: Optional[str] = None,
    ) -> List[dict]:
        """
        Find existing vectors that are similar to the query above a threshold.
        Used for deduplication before upserting new facts.

        Args:
            query_embedding: The embedding to compare against.
            user_id: The user ID to scope the search.
            threshold: Cosine similarity threshold (0-1).
            top_k: Maximum candidates to check.
            bot_id: Optional ID of the bot to scope the search.

        Returns:
            List of dicts with 'text', 'score', and 'node_id' for matches above threshold.
        """
        try:
            filters_list = [ExactMatchFilter(key="user_id", value=str(user_id))]
            if bot_id:
                filters_list.append(ExactMatchFilter(key="bot_id", value=str(bot_id)))

            filters = MetadataFilters(filters=filters_list)

            query_obj = VectorStoreQuery(
                query_embedding=query_embedding,
                similarity_top_k=top_k,
                filters=filters,
            )

            result = await asyncio.to_thread(self._store.query, query_obj)

            similar: List[dict] = []
            if result.nodes and result.similarities:
                for node, score in zip(result.nodes, result.similarities):
                    if score is not None and score >= threshold:
                        similar.append(
                            {
                                "text": node.get_content(),
                                "score": score,
                                "node_id": getattr(node, "node_id", None),
                            }
                        )
            return similar
        except Exception as e:
            logger.error(f"Error finding similar vectors: {e}", exc_info=True)
            return []

    async def fetch_neighbors(
        self,
        conversation_id: str,
        chunk_index: int,
        user_id: str,
        radius: int = 1,
    ) -> List[dict]:
        """
        Fetch chunks adjacent to a given chunk_index in the same conversation.

        Used for "embed small, retrieve larger" pattern — when a small chunk
        matches a query, also return its neighboring chunks for richer context.

        Args:
            conversation_id: The conversation the chunk belongs to.
            chunk_index: The 0-based index of the matched chunk.
            user_id: The user ID to scope the query.
            radius: How many neighbors on each side (1 = ±1 chunk).

        Returns:
            List of dicts with 'text' and 'first_timestamp' keys,
            ordered by chunk_index ascending.
        """
        try:
            table_name = self._store.table_name

            def _fetch():
                with self._store._session() as session:
                    sql = (
                        f'SELECT text, metadata_ FROM public."data_{table_name}" '
                        f"WHERE metadata_->>'conversation_id' = :conv_id "
                        f"AND metadata_->>'user_id' = :uid "
                        f"AND CAST(metadata_->>'chunk_index' AS INTEGER) "
                        f"BETWEEN :min_idx AND :max_idx "
                        f"ORDER BY CAST(metadata_->>'chunk_index' AS INTEGER)"
                    )
                    result = session.execute(sql_text(sql), {
                        "conv_id": str(conversation_id),
                        "uid": str(user_id),
                        "min_idx": max(0, chunk_index - radius),
                        "max_idx": chunk_index + radius,
                    })
                    rows = []
                    for row in result:
                        # row might be a Row object or a Mapping
                        meta = row.metadata_ if hasattr(row, 'metadata_') else {}
                        rows.append({
                            "text": row.text if hasattr(row, 'text') else "",
                            "first_timestamp": meta.get("first_timestamp", "") if isinstance(meta, dict) else "",
                        })
                    return rows

            return await asyncio.to_thread(_fetch)
        except Exception as e:
            logger.error(
                "Error fetching neighbors for conversation %s, chunk %d: %s",
                conversation_id, chunk_index, e, exc_info=True,
            )
            return []