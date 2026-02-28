"""
LlamaIndex-based memory manager implementation.

This module provides the `LlamaIndexMemoryManager` class, which orchestrates
the memory system. It supports both legacy per-message storage (add_message)
and the new chunked fact extraction approach (extract_and_store_memories).
"""

import logging
from datetime import datetime
from typing import List, Any, Optional

from llama_index.core.schema import TextNode
from core.abstractions import VectorStore, EmbeddingModel, SummarizationModel
from storage.interfaces import MessageRepo, ConversationRepo, UserRepo

logger = logging.getLogger(__name__)


class LlamaIndexMemoryManager:
    """
    LlamaIndexMemoryManager implementation.

    Orchestrates memory creation via chunked fact extraction from conversations,
    with deduplication against existing memory entries.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_model: EmbeddingModel,
        summarization_model: SummarizationModel,
        message_repo: MessageRepo,
        conversation_repo: ConversationRepo,
        user_repo: UserRepo,
        dedup_threshold: float = 0.85,
    ):
        """
        Initialize the LlamaIndexMemoryManager.

        Args:
            vector_store: The vector store to use.
            embedding_model: The embedding model to use.
            summarization_model: The summarization model to use.
            message_repo: The message repository.
            conversation_repo: The conversation repository.
            user_repo: The user repository.
            dedup_threshold: Cosine similarity threshold for deduplication.
        """
        self._vector_store = vector_store
        self._embedding_model = embedding_model
        self._summarization_model = summarization_model
        self._message_repo = message_repo
        self._conversation_repo = conversation_repo
        self._user_repo = user_repo
        self._dedup_threshold = dedup_threshold

    async def add_message(self, user_id: str, message: str, bot_id: str = None) -> None:
        """
        Legacy method: Add a single message as a vector memory.
        Kept for backward compatibility; prefer extract_and_store_memories().

        Args:
            user_id: The ID of the user.
            message: The message to add.
            bot_id: Optional ID of the bot.
        """
        embedding = await self._embedding_model.get_embedding(message)
        metadata = {"user_id": str(user_id)}
        if bot_id:
            metadata["bot_id"] = str(bot_id)

        node = TextNode(
            text=message,
            embedding=embedding,
            metadata=metadata,
        )
        await self._vector_store.upsert([node])

    async def extract_and_store_memories(self, user_id: str, facts: list, bot_id: str = None) -> int:
        """
        Store extracted memory facts into the vector store with deduplication.

        Each fact is embedded, checked against existing entries for the user (and bot, if provided),
        and only stored if sufficiently novel (below the dedup threshold).

        Args:
            user_id: The ID of the user.
            facts: List of MemoryFact-like objects with fields:
                   - fact (str)
                   - category (str, optional)
                   - source_message_ids (list[str], optional)
            bot_id: Optional ID of the bot to scope / tag memories.

        Returns:
            Number of new facts actually stored (after dedup filtering).
        """
        stored_count = 0

        for fact in facts:
            try:
                fact_text = getattr(fact, "fact", None) or str(fact)
                if not fact_text:
                    continue

                # Embed the fact text
                embedding = await self._embedding_model.get_embedding(fact_text)
                if not embedding:
                    logger.warning(f"Failed to embed fact: {fact_text[:50]}...")
                    continue

                # Dedup check (if vector store supports it)
                if hasattr(self._vector_store, "find_similar"):
                    duplicates = await self._vector_store.find_similar(
                        embedding,
                        user_id=str(user_id),
                        threshold=self._dedup_threshold,
                        top_k=3,
                    )
                    if duplicates:
                        logger.info(
                            f"Skipping duplicate fact (score={duplicates[0]['score']:.3f}): "
                            f"{fact_text[:60]}... ≈ {duplicates[0].get('text','')[:60]}..."
                        )
                        continue

                category = getattr(fact, "category", None) or "unknown"
                source_message_ids = getattr(fact, "source_message_ids", None) or []
                if not isinstance(source_message_ids, list):
                    source_message_ids = []

                metadata = {
                    "user_id": str(user_id),
                    "category": str(category),
                    "created_at": datetime.utcnow().isoformat(),
                    "source_message_ids": ",".join([str(x) for x in source_message_ids[:5]]),
                }
                if bot_id:
                    metadata["bot_id"] = str(bot_id)

                node = TextNode(
                    text=fact_text,
                    embedding=embedding,
                    metadata=metadata,
                )

                await self._vector_store.upsert([node])
                stored_count += 1
                logger.info(f"Stored memory fact [{category}]: {fact_text[:80]}...")

            except Exception as e:
                logger.error(f"Failed to store fact '{str(getattr(fact, 'fact', fact))[:50]}...': {e}", exc_info=True)
                continue

        logger.info(f"Stored {stored_count}/{len(facts)} facts for user {user_id} (bot_id={bot_id})")
        return stored_count

    async def get_context(self, user_id: str, query: str, top_k: int, bot_id: str = None) -> str:
        """
        Get context for a query by searching the vector store.

        Args:
            user_id: The ID of the user.
            query: The query to get context for.
            top_k: The number of top results to return.
            bot_id: Optional ID of the bot to filter memories for.

        Returns:
            The context string assembled from matching memories.
        """
        logger.info(f"==> get_context called with user_id='{user_id}', bot_id='{bot_id}', top_k={top_k}")
        try:
            query_embedding = await self._embedding_model.get_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding. Returning empty context.")
                return ""
            logger.info(f"Query embedding generated (length: {len(query_embedding)})")

            nodes = await self._vector_store.query(
                query_embedding=query_embedding,
                top_k=top_k,
                user_id=str(user_id),
                bot_id=str(bot_id) if bot_id else None,
            )
            logger.info(f"<== Vector store query returned {len(nodes)} nodes")

            if not nodes:
                return ""

            return "\n".join([node.get_content() for node in nodes])
        except Exception as e:
            logger.error(f"Error in get_context: {e}", exc_info=True)
            return ""

    async def trigger_summarization(self, user_id: str, prompt_template: str, bot_id: str = None) -> None:
        """
        Trigger summarization for a user (legacy path, kept for Celery task compatibility).

        Args:
            user_id: The ID of the user.
            prompt_template: The prompt template to use for summarization.
            bot_id: Optional ID of the bot.
        """
        user = await self._user_repo.get_user_by_username(user_id)
        if not user:
            return

        conversations = await self._conversation_repo.list_conversations(str(user.id))
        if not conversations:
            return

        conversation_id = str(conversations[0].id)
        messages = await self._message_repo.list_messages(conversation_id)
        text_to_summarize = "\n".join([msg.content for msg in messages])

        summary = await self._summarization_model.summarize(
            text_to_summarize, prompt_template, user_id=user_id
        )
        await self.add_message(user_id, f"Summary: {summary}", bot_id=bot_id)

    async def clear_memories(self, user_id: str, bot_id: str = None) -> None:
        """
        Clear all memories for a user.

        Args:
            user_id: The ID of the user.
            bot_id: Optional ID of the bot.
        """
        await self._vector_store.clear(str(user_id), bot_id=str(bot_id) if bot_id else None)