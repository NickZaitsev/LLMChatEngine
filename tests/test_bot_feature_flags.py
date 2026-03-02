import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot import AIGirlfriendBot
from features import BotFeature, DEFAULT_FEATURE_FLAGS


@pytest.fixture
def bot_instance():
    with patch.dict(os.environ, {
        "TELEGRAM_TOKEN": "test_token",
        "DATABASE_URL": "postgresql://test:test@test:5432/test",
    }):
        with patch("bot.PostgresConversationManager") as mock_cm, \
             patch("bot.AIHandler") as mock_ai_handler, \
             patch("bot.TypingIndicatorManager") as mock_typing_manager, \
             patch("bot.MessageQueueManager"), \
             patch("bot.MessageDispatcher"), \
             patch("bot.BufferManager") as mock_buffer_manager:
            conversation_manager = MagicMock()
            conversation_manager.get_conversation_async = AsyncMock()
            conversation_manager.clear_conversation_async = AsyncMock()
            conversation_manager.add_message_async = AsyncMock()
            conversation_manager.get_formatted_conversation_async = AsyncMock(return_value=[])
            conversation_manager._ensure_user_and_conversation = AsyncMock()
            mock_cm.return_value = conversation_manager

            typing_manager = MagicMock()
            typing_manager.stop_typing = AsyncMock()
            mock_typing_manager.return_value = typing_manager

            buffer_manager = MagicMock()
            buffer_manager.set_user_context = MagicMock()
            buffer_manager.add_message = AsyncMock()
            buffer_manager.schedule_dispatch = AsyncMock()
            mock_buffer_manager.return_value = buffer_manager

            bot = AIGirlfriendBot()
            bot.bot_id = uuid.uuid4()
            bot.bot_config = SimpleNamespace(feature_flags=dict(DEFAULT_FEATURE_FLAGS))
            bot.conversation_manager = conversation_manager
            bot.typing_manager = typing_manager
            bot.buffer_manager = buffer_manager
            bot.ai_handler = mock_ai_handler.return_value
            bot.proactive_messaging_service = None
            yield bot


@pytest.mark.asyncio
async def test_ok_command_clears_memories_for_current_bot(bot_instance):
    user_id = 12345
    bot_instance.pending_clear_confirmation.add(user_id)
    bot_instance.conversation_manager.get_conversation_async = AsyncMock(return_value=["msg"])
    bot_instance.conversation_manager.clear_conversation_async = AsyncMock()
    bot_instance.memory_manager = MagicMock()
    bot_instance.memory_manager.clear_memories = AsyncMock()

    update = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat.id = 67890
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    await bot_instance.ok_command(update, context)

    bot_instance.memory_manager.clear_memories.assert_awaited_once_with(
        str(user_id),
        bot_id=str(bot_instance.bot_id),
    )


@pytest.mark.asyncio
async def test_personality_command_respects_feature_flag(bot_instance):
    bot_instance.bot_config.feature_flags[BotFeature.PERSONALITY_SWITCH.value] = False

    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat.id = 67890
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.bot.send_chat_action = AsyncMock()

    await bot_instance.personality_command(update, context)

    update.message.reply_text.assert_awaited_once_with(
        "❌ Personality switching is disabled for this bot."
    )


@pytest.mark.asyncio
async def test_handle_message_bypasses_buffer_when_feature_disabled(bot_instance):
    bot_instance.bot_config.feature_flags[BotFeature.BUFFER_MANAGER.value] = False
    bot_instance._generate_and_send_response = AsyncMock()

    update = MagicMock()
    update.effective_user.id = 12345
    update.effective_chat.id = 67890
    update.message.text = "hello"

    context = MagicMock()
    context.bot = MagicMock()

    await bot_instance.handle_message(update, context)

    bot_instance._generate_and_send_response.assert_awaited_once_with(
        12345,
        67890,
        context.bot,
        "hello",
    )
    bot_instance.buffer_manager.add_message.assert_not_called()
    bot_instance.buffer_manager.schedule_dispatch.assert_not_called()
