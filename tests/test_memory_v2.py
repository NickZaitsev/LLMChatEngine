"""
Integration tests for the LlamaIndex-based memory system (v2 — direct embedding).
"""

import pytest
from datetime import datetime
from uuid import uuid4
from app_context import get_app_context
from memory.adaptive_chunker import ConversationChunk


@pytest.mark.asyncio
async def test_memory_system_integration():
    """
    Tests the full flow of the LlamaIndex-based memory system:
    1. Storing a conversation chunk.
    2. Retrieving context for a related query.
    3. Clearing the memories for a user.
    """
    app_context = await get_app_context()
    memory_manager = app_context.memory_manager

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