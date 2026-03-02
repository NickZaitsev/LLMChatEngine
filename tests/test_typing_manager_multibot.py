import asyncio
from unittest.mock import AsyncMock

import pytest

from message_manager import TypingIndicatorManager


@pytest.mark.asyncio
async def test_typing_indicator_manager_isolates_routes_in_same_chat():
    typing_manager = TypingIndicatorManager()
    typing_manager.typing_interval = 0.01

    bot_a = AsyncMock()
    bot_a.send_chat_action = AsyncMock()
    bot_b = AsyncMock()
    bot_b.send_chat_action = AsyncMock()

    chat_id = 12345

    await typing_manager.start_typing(bot_a, chat_id, route_key="12345:bot-a")
    await typing_manager.start_typing(bot_b, chat_id, route_key="12345:bot-b")
    await asyncio.sleep(0.03)

    assert typing_manager.is_typing_active(chat_id, route_key="12345:bot-a")
    assert typing_manager.is_typing_active(chat_id, route_key="12345:bot-b")
    assert bot_a.send_chat_action.await_count > 0
    assert bot_b.send_chat_action.await_count > 0

    await typing_manager.stop_typing(chat_id, route_key="12345:bot-a")
    assert not typing_manager.is_typing_active(chat_id, route_key="12345:bot-a")
    assert typing_manager.is_typing_active(chat_id, route_key="12345:bot-b")

    await typing_manager.cleanup()


@pytest.mark.asyncio
async def test_typing_indicator_manager_reports_and_cleans_up_real_chat_ids():
    typing_manager = TypingIndicatorManager()
    typing_manager.typing_interval = 0.01

    bot_a = AsyncMock()
    bot_a.send_chat_action = AsyncMock()
    bot_b = AsyncMock()
    bot_b.send_chat_action = AsyncMock()

    await typing_manager.start_typing(bot_a, 12345, route_key="12345:bot-a")
    await typing_manager.start_typing(bot_b, 67890, route_key="67890:bot-b")
    await asyncio.sleep(0.03)

    assert typing_manager.get_active_typing_chats() == {12345, 67890}

    await typing_manager.stop_all_typing()

    assert not typing_manager.is_typing_active(12345, route_key="12345:bot-a")
    assert not typing_manager.is_typing_active(67890, route_key="67890:bot-b")
