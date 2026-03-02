from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from storage_conversation_manager import PostgresConversationManager


@pytest.mark.asyncio
async def test_ensure_user_and_conversation_refreshes_cached_conversation():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    cached = SimpleNamespace(id="conv-1", last_memorized_message_id=None)
    refreshed = SimpleNamespace(id="conv-1", last_memorized_message_id="msg-2")

    manager.storage = MagicMock()
    manager.storage.conversations.get_conversation = AsyncMock(return_value=refreshed)
    manager._conversation_cache[(123, None)] = cached

    conversation = await manager._ensure_user_and_conversation(123)

    assert conversation is refreshed
    assert manager._conversation_cache[(123, None)].last_memorized_message_id == "msg-2"
    manager.storage.conversations.get_conversation.assert_awaited_once_with("conv-1")


@pytest.mark.asyncio
async def test_clear_conversation_deletes_default_bot_user_history():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    conversation = SimpleNamespace(id="conv-1")

    manager.storage = MagicMock()
    manager.storage.messages.delete_messages = AsyncMock(return_value=4)
    manager.storage.message_history.clear_user_history = AsyncMock(return_value=3)
    manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)

    await manager.clear_conversation_async(123)

    manager.storage.messages.delete_messages.assert_awaited_once_with("conv-1")
    manager.storage.message_history.clear_user_history.assert_awaited_once_with(
        uuid.uuid5(uuid.NAMESPACE_OID, "telegram_user_123"),
        bot_id=None,
    )


@pytest.mark.asyncio
async def test_clear_conversation_deletes_bot_scoped_user_history():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    conversation = SimpleNamespace(id="conv-1")
    bot_id = "11111111-1111-1111-1111-111111111111"

    manager.storage = MagicMock()
    manager.storage.messages.delete_messages = AsyncMock(return_value=4)
    manager.storage.message_history.clear_user_history = AsyncMock(return_value=2)
    manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)

    await manager.clear_conversation_async(123, bot_id=bot_id)

    manager.storage.message_history.clear_user_history.assert_awaited_once()
