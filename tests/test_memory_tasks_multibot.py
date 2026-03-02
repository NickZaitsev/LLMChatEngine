from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from memory.tasks import create_conversation_summary_async


@pytest.mark.asyncio
async def test_create_conversation_summary_uses_bot_scoped_ai_runtime():
    conversation = SimpleNamespace(
        id="conv-1",
        bot_id="11111111-1111-1111-1111-111111111111",
        summary=None,
        last_summarized_message_id=None,
    )
    messages = [
        SimpleNamespace(id="msg-1", role="user", content="Hello"),
        SimpleNamespace(id="msg-2", role="assistant", content="Hi"),
    ]

    ai_handler = MagicMock()
    ai_handler.get_response = AsyncMock(return_value="summary")

    app_context = MagicMock()
    app_context.get_ai_runtime_for_bot = AsyncMock(return_value=(ai_handler, None))
    app_context.conversation_manager.storage.conversations.get_conversation = AsyncMock(return_value=conversation)
    app_context.conversation_manager.storage.conversations.update_conversation = AsyncMock()
    app_context.conversation_manager.storage.messages.get_messages_for_summary = AsyncMock(return_value=messages)

    with patch("memory.tasks.get_app_context", AsyncMock(return_value=app_context)):
        await create_conversation_summary_async("conv-1")

    app_context.get_ai_runtime_for_bot.assert_awaited_once_with(conversation.bot_id)
    ai_handler.get_response.assert_awaited_once()
