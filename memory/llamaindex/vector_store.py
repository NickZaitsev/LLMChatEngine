"""
LlamaIndex PGVector store implementation.

This module provides the `PgVectorStore` class, which implements the
`VectorStore` abstraction for a PostgreSQL database with the pgvector
extension. It handles the connection to the database and provides methods
for upserting, querying, and clearing vector data.
"""

from typing import List, Any
import sqlalchemy
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.core.vector_stores import (
    VectorStoreQuery,
    MetadataFilters,
    ExactMatchFilter,
)
from sqlalchemy.engine.url import make_url
from core.abstractions import VectorStore as VectorStoreAbstraction
import config

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
        self._store.add(nodes)

    async def query(
        self, query_embedding: List[float], top_k: int, user_id: str
    ) -> List[Any]:
        """
        Query the vector store for similar nodes.

        Args:
            query_embedding: The query embedding.
            top_k: The number of top results to return.
            user_id: The ID of the user to filter memories for.

        Returns:
            A list of similar nodes.
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"==> PGVectorStore querying with user_id='{user_id}', top_k={top_k}")
        try:
            filters = MetadataFilters(
                filters=[ExactMatchFilter(key="user_id", value=str(user_id))]
            )
            logger.info(f"Constructed metadata filters: {filters}")
            query_obj = VectorStoreQuery(
                query_embedding=query_embedding, similarity_top_k=top_k, filters=filters
            )
            logger.info(f"Executing vector store query with top_k={query_obj.similarity_top_k}")
            result = self._store.query(query_obj)
            logger.info(f"<== PGVectorStore query returned {len(result.nodes)} nodes")
            return result.nodes
        except Exception as e:
            logger.error(f"Error in vector store query: {e}", exc_info=True)
            raise

    async def clear(self, user_id: str) -> None:
        """
        Clear all nodes for a specific user from the vector store.

        Args:
            user_id: The ID of the user whose data should be cleared.
        """
        # This is a bit of a hack, as LlamaIndex's PGVectorStore doesn't
        # directly support deleting by user_id. We'll need to add a
        # user_id column to the vector store table and delete based on that.
        # For now, we'll just log a warning.
        print(f"WARNING: Clearing vector store for user {user_id} is not yet implemented.")
