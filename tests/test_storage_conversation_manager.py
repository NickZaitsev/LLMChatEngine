import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from storage_conversation_manager import PostgresConversationManager


@pytest.mark.asyncio
async def test_ensure_user_and_conversation_refreshes_cached_conversation():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    conversation_id = uuid.uuid4()
    refreshed = SimpleNamespace(id=conversation_id, last_memorized_message_id="msg-2")

    manager.storage = MagicMock()
    manager.storage.conversations.get_conversation = AsyncMock(return_value=refreshed)
    manager._conversation_id_cache[(123, None)] = conversation_id

    conversation = await manager._ensure_user_and_conversation(123)

    assert conversation is refreshed
    assert manager._conversation_id_cache[(123, None)] == conversation_id
    manager.storage.conversations.get_conversation.assert_awaited_once_with(str(conversation_id))


@pytest.mark.asyncio
async def test_ensure_user_and_conversation_does_not_create_default_persona():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    user = SimpleNamespace(id=uuid.uuid4(), username="123")
    conversation = SimpleNamespace(id=uuid.uuid4(), persona_id=None)

    manager.storage = MagicMock()
    manager.storage.users.get_user_by_username = AsyncMock(return_value=user)
    manager.storage.conversations.list_conversations = AsyncMock(return_value=[])
    manager.storage.conversations.create_conversation = AsyncMock(return_value=conversation)
    manager.storage.personas.create_persona = AsyncMock()
    manager.storage.personas.list_personas = AsyncMock()

    result = await manager._ensure_user_and_conversation(123)

    assert result is conversation
    manager.storage.personas.list_personas.assert_not_called()
    manager.storage.personas.create_persona.assert_not_called()
    manager.storage.conversations.create_conversation.assert_awaited_once_with(
        user_id=str(user.id),
        bot_id=None,
        title="Chat with 123",
        extra_data={"auto_created": True},
    )


@pytest.mark.asyncio
async def test_clear_conversation_deletes_default_bot_user_history():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    conversation = SimpleNamespace(id="conv-1")

    manager.storage = MagicMock()
    manager.storage.messages.delete_messages = AsyncMock(return_value=4)
    manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)

    await manager.clear_conversation_async(123)

    manager.storage.messages.delete_messages.assert_awaited_once_with("conv-1")


@pytest.mark.asyncio
async def test_clear_conversation_deletes_bot_scoped_user_history():
    manager = PostgresConversationManager("postgresql://u:p@h:5432/db", use_pgvector=False)
    conversation = SimpleNamespace(id="conv-1")
    bot_id = "11111111-1111-1111-1111-111111111111"

    manager.storage = MagicMock()
    manager.storage.messages.delete_messages = AsyncMock(return_value=4)
    manager._ensure_user_and_conversation = AsyncMock(return_value=conversation)

    await manager.clear_conversation_async(123, bot_id=bot_id)

    manager.storage.messages.delete_messages.assert_awaited_once_with("conv-1")
