"""
Integration tests for the LlamaIndex-based memory system (v2 — direct embedding).
"""

import pytest
from datetime import datetime
from uuid import uuid4
from memory.adaptive_chunker import ConversationChunk
from memory.manager import LlamaIndexMemoryManager


class InMemoryVectorStore:
    """In-memory vector store for deterministic memory manager integration tests."""

    def __init__(self):
        """Initialize an empty node collection."""
        self._nodes = []

    async def upsert(self, nodes):
        """Store nodes in memory."""
        self._nodes.extend(nodes)

    async def query(self, query_embedding, top_k, user_id, bot_id=None):
        """Return stored nodes scoped by user and optional bot."""
        matches = [
            node
            for node in self._nodes
            if node.metadata.get("user_id") == str(user_id)
            and (bot_id is None or node.metadata.get("bot_id") == str(bot_id))
        ]
        return matches[:top_k]

    async def clear(self, user_id, bot_id=None):
        """Remove stored nodes scoped by user and optional bot."""
        self._nodes = [
            node
            for node in self._nodes
            if not (
                node.metadata.get("user_id") == str(user_id)
                and (bot_id is None or node.metadata.get("bot_id") == str(bot_id))
            )
        ]


class DeterministicEmbeddingModel:
    """Embedding model that returns deterministic local vectors."""

    async def get_embedding(self, text):
        """Return a deterministic embedding for one text value."""
        return [float(len(text) % 10), 1.0, 0.0]

    async def get_embeddings(self, texts):
        """Return deterministic embeddings for several text values."""
        return [await self.get_embedding(text) for text in texts]


@pytest.mark.asyncio
async def test_memory_system_integration():
    """
    Tests the full flow of the LlamaIndex-based memory system:
    1. Storing a conversation chunk.
    2. Retrieving context for a related query.
    3. Clearing the memories for a user.
    """
    memory_manager = LlamaIndexMemoryManager(
        vector_store=InMemoryVectorStore(),
        embedding_model=DeterministicEmbeddingModel(),
        expand_neighbors=0,
    )

    user_id = "test_user_123"
    conversation_id = str(uuid4())
    now = datetime.now()

    # 1. Store a conversation chunk
    chunk = ConversationChunk(
        text="user: My favorite color is magenta.\nassistant: Magenta is a beautiful color!",
        message_ids=[str(uuid4()), str(uuid4())],
        token_count=20,
        chunk_index=0,
        first_timestamp=now,
        last_timestamp=now,
    )
    stored = await memory_manager.store_conversation_chunks(
        user_id=user_id,
        chunks=[chunk],
        conversation_id=conversation_id,
    )
    assert stored == 1

    # 2. Retrieve the context for a query
    query = "What is my favorite color?"
    context = await memory_manager.get_context(user_id, query, top_k=1)

    # Assert that the context contains the fact
    assert "magenta" in context.lower(), "The color fact should be present in the retrieved context."

    # 3. Clear the memories for the user
    await memory_manager.clear_memories(user_id)

    # 4. Retrieve the context again
    context_after_clear = await memory_manager.get_context(user_id, query, top_k=1)

    # Assert that the context is now empty or does not contain the fact
    assert "magenta" not in context_after_clear.lower(), "The fact should not be present after clearing memories."
