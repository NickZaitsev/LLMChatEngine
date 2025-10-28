"""
Tests for the new LlamaIndex-based memory system.
"""

import pytest
from app_context import get_app_context

@pytest.mark.asyncio
async def test_memory_system_integration():
    """
    Tests the full flow of the LlamaIndex-based memory system:
    1. Adding a message to the memory.
    2. Retrieving the context for a query.
    3. Clearing the memories for a user.
    """
    app_context = await get_app_context()
    memory_manager = app_context.memory_manager

    user_id = "test_user_123"
    unique_fact = "My favorite color is magenta."

    # 1. Add a message to the memory
    await memory_manager.add_message(user_id, unique_fact)

    # 2. Retrieve the context for a query
    query = "What is my favorite color?"
    context = await memory_manager.get_context(user_id, query, top_k=1)

    # Assert that the context contains the unique fact
    assert unique_fact in context, "The unique fact should be present in the retrieved context."

    # 3. Clear the memories for the user
    await memory_manager.clear_memories(user_id)

    # 4. Retrieve the context again
    context_after_clear = await memory_manager.get_context(user_id, query, top_k=1)

    # Assert that the context is now empty or does not contain the fact
    assert unique_fact not in context_after_clear, "The unique fact should not be present after clearing memories."