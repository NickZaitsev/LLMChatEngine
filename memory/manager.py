"""
LlamaIndex-based memory manager implementation.

This module provides the `LlamaIndexMemoryManager` class, which orchestrates
the new memory system using the abstractions for the vector store, embedding
model, and summarization model.
"""

from typing import List, Any, Dict
from llama_index.core.schema import TextNode
from core.abstractions import VectorStore, EmbeddingModel, SummarizationModel
from storage.interfaces import MessageRepo, ConversationRepo, UserRepo

class LlamaIndexMemoryManager:
    """
    LlamaIndexMemoryManager implementation.
    """

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_model: EmbeddingModel,
        summarization_model: SummarizationModel,
        message_repo: MessageRepo,
        conversation_repo: ConversationRepo,
        user_repo: UserRepo,
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
        """
        self._vector_store = vector_store
        self._embedding_model = embedding_model
        self._summarization_model = summarization_model
        self._message_repo = message_repo
        self._conversation_repo = conversation_repo
        self._user_repo = user_repo

    async def add_message(self, user_id: str, message: str) -> None:
        """
        Add a message to the memory.

        Args:
            user_id: The ID of the user.
            message: The message to add.
        """
        embedding = await self._embedding_model.get_embedding(message)
        node = TextNode(
            text=message,
            embedding=embedding,
            metadata={"user_id": user_id},
        )
        await self._vector_store.upsert([node])

    async def get_context(self, user_id: str, query: str, top_k: int) -> str:
        """
        Get context for a query.

        Args:
            user_id: The ID of the user.
            query: The query to get context for.
            top_k: The number of top results to return.

        Returns:
            The context for the query.
        """
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"==> get_context called with user_id='{user_id}', top_k={top_k}")
        try:
            query_embedding = await self._embedding_model.get_embedding(query)
            if not query_embedding:
                logger.warning("Failed to generate query embedding. Returning empty context.")
                return ""
            logger.info(f"Query embedding generated (length: {len(query_embedding)})")
            
            logger.info(f"==> Calling vector_store.query with user_id='{user_id}'")
            nodes = await self._vector_store.query(query_embedding, top_k, user_id)
            logger.info(f"<== Vector store query returned {len(nodes)} nodes")

            if not nodes:
                logger.warning("Vector store returned no nodes.")
                return ""

            context = "\n".join([node.get_content() for node in nodes])
            logger.info(f"Context assembled (length: {len(context)})")
            return context
        except Exception as e:
            logger.error(f"Error in get_context: {e}", exc_info=True)
            return ""

    async def trigger_summarization(self, user_id: str, prompt_template: str) -> None:
        """
        Trigger summarization for a user.

        Args:
            user_id: The ID of the user.
            prompt_template: The prompt template to use for summarization.
        """
        # Get user by username (telegram ID) to find the internal user UUID
        user = await self._user_repo.get_user_by_username(user_id)
        if not user:
            return  # No user found, so no conversations to summarize

        # Use the internal user ID (UUID) to list conversations
        conversations = await self._conversation_repo.list_conversations(str(user.id))
        if not conversations:
            return

        conversation_id = str(conversations[0].id)
        messages = await self._message_repo.list_messages(conversation_id)
        text_to_summarize = "\n".join([msg.content for msg in messages])
        summary = await self._summarization_model.summarize(
            text_to_summarize, prompt_template, user_id=user_id
        )
        await self.add_message(user_id, f"Summary: {summary}")

    async def clear_memories(self, user_id: str) -> None:
        """
        Clear all memories for a user.

        Args:
            user_id: The ID of the user.
        """
        await self._vector_store.clear(user_id)