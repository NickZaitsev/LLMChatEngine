"""
Memory manager for direct conversation chunk embedding.

This module provides the `LlamaIndexMemoryManager` class that handles
storing pre-chunked conversation fragments as vectors and retrieving
them with neighbor expansion for richer context.

No LLM-based fact extraction — conversation chunks are embedded as-is.
"""

import logging
from typing import List, Any, Optional

from llama_index.core.schema import TextNode
from core.abstractions import VectorStore, EmbeddingModel

logger = logging.getLogger(__name__)


class LlamaIndexMemoryManager:
    """
    Orchestrates memory storage and retrieval with:
    - Batch embedding of conversation chunks
    - Bulk upsert into pgvector
    - Neighbor expansion at retrieval time
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_model: EmbeddingModel,
        expand_neighbors: int = 1,
    ):
        """
        Initialize the LlamaIndexMemoryManager.

        Args:
            vector_store: The vector store for persistence (pgvector).
            embedding_model: The embedding model (LMStudio or Gemini).
            expand_neighbors: Radius for neighbor expansion at retrieval.
                              0 = disabled, 1 = fetch ±1 chunk, etc.
        """
        self._vector_store = vector_store
        self._embedding_model = embedding_model
        self._expand_neighbors = expand_neighbors

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    async def store_conversation_chunks(
        self,
        user_id: str,
        chunks: list,
        conversation_id: str,
        bot_id: Optional[str] = None,
    ) -> int:
        """
        Batch-embed and store conversation chunks.

        1. Batch-embed all chunk texts in one API call.
        2. Build TextNodes with metadata.
        3. Bulk upsert all nodes at once.

        Args:
            user_id: The ID of the user.
            chunks: List of ConversationChunk objects from AdaptiveChunker.
            conversation_id: The conversation these chunks belong to.
            bot_id: Optional bot ID for multi-bot support.

        Returns:
            Number of chunks successfully stored.
        """
        if not chunks:
            return 0

        # 1. Batch embed (1 API call instead of N)
        texts = [chunk.text for chunk in chunks]
        try:
            embeddings = await self._embedding_model.get_embeddings(texts)
        except Exception as e:
            logger.error("Batch embedding failed: %s", e, exc_info=True)
            return 0

        # 2. Build TextNodes with metadata
        nodes: List[TextNode] = []
        for chunk, embedding in zip(chunks, embeddings):
            if not embedding:
                logger.warning(
                    "Empty embedding for chunk %d, skipping", chunk.chunk_index
                )
                continue

            metadata = {
                "user_id": str(user_id),
                "conversation_id": str(conversation_id),
                "chunk_index": str(chunk.chunk_index),
                "message_ids": ",".join(chunk.message_ids[:10]),
                "first_timestamp": chunk.first_timestamp.isoformat(),
                "last_timestamp": chunk.last_timestamp.isoformat(),
            }
            if bot_id:
                metadata["bot_id"] = str(bot_id)

            nodes.append(TextNode(
                text=chunk.text,
                embedding=embedding,
                metadata=metadata,
            ))

        # 3. Bulk upsert (1 DB call instead of N)
        if nodes:
            await self._vector_store.upsert(nodes)
            logger.info(
                "Stored %d conversation chunk(s) for user %s (conversation %s)",
                len(nodes), user_id, str(conversation_id)[:8],
            )

        return len(nodes)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    async def get_context(
        self,
        user_id: str,
        query: str,
        top_k: int,
        bot_id: Optional[str] = None,
    ) -> str:
        """
        Get memory context for a query by searching the vector store,
        then optionally expanding results with neighboring chunks.

        Args:
            user_id: The ID of the user.
            query: The query text (e.g. last user message).
            top_k: Number of top results to return.
            bot_id: Optional bot ID for multi-bot filtering.

        Returns:
            Concatenated context string from matching (and neighboring) chunks.
        """
        logger.info(
            "==> get_context called with user_id='%s', bot_id='%s', top_k=%d",
            user_id, bot_id, top_k,
        )

        try:
            query_embedding = await self._embedding_model.get_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding. Returning empty context.")
                return ""
            logger.info("Query embedding generated (length: %d)", len(query_embedding))

            nodes = await self._vector_store.query(
                query_embedding=query_embedding,
                top_k=top_k,
                user_id=str(user_id),
                bot_id=str(bot_id) if bot_id else None,
            )
            logger.info("<== Vector store query returned %d nodes", len(nodes))

            if not nodes:
                return ""

            # ----- Neighbor expansion -----
            if (
                self._expand_neighbors > 0
                and hasattr(self._vector_store, "fetch_neighbors")
            ):
                return await self._expand_and_merge(nodes, user_id)

            # No expansion — just return matching chunks
            return "\n---\n".join(node.get_content() for node in nodes)

        except Exception as e:
            logger.error("Error in get_context: %s", e, exc_info=True)
            return ""

    async def _expand_and_merge(self, nodes: List[Any], user_id: str) -> str:
        """
        For each matched node, fetch its neighboring chunks and merge
        everything into a deduplicated, timestamp-ordered result.
        """
        seen_texts: set = set()
        all_results: List[dict] = []  # [{"text": ..., "timestamp": ...}]

        for node in nodes:
            conv_id = node.metadata.get("conversation_id")
            chunk_idx_str = node.metadata.get("chunk_index")

            if conv_id and chunk_idx_str is not None:
                try:
                    chunk_idx = int(chunk_idx_str)
                except (ValueError, TypeError):
                    chunk_idx = None

                if chunk_idx is not None:
                    neighbors = await self._vector_store.fetch_neighbors(
                        conversation_id=conv_id,
                        chunk_index=chunk_idx,
                        user_id=str(user_id),
                        radius=self._expand_neighbors,
                    )
                    for n in neighbors:
                        text = n.get("text", "")
                        if text and text not in seen_texts:
                            seen_texts.add(text)
                            all_results.append({
                                "text": text,
                                "timestamp": n.get("first_timestamp", ""),
                            })
                    continue  # neighbors already include the original chunk

            # Fallback — no metadata for expansion (e.g. old-format entries)
            text = node.get_content()
            if text and text not in seen_texts:
                seen_texts.add(text)
                all_results.append({
                    "text": text,
                    "timestamp": node.metadata.get("first_timestamp", ""),
                })

        # Sort by timestamp so context reads chronologically
        all_results.sort(key=lambda r: r["timestamp"])

        return "\n---\n".join(r["text"] for r in all_results)

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    async def clear_memories(self, user_id: str, bot_id: Optional[str] = None) -> None:
        """
        Clear all memories for a user.

        Args:
            user_id: The ID of the user.
            bot_id: Optional bot ID to scope the clearing.
        """
        await self._vector_store.clear(
            str(user_id),
            bot_id=str(bot_id) if bot_id else None,
        )