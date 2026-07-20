import asyncio
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import bot
from bot import TelegramChatBot


def test_bot_module_has_no_ad_hoc_asyncio_run_cleanup():
    source = inspect.getsource(bot)
    assert "asyncio.run(" not in source
    assert "shutdown_handler" not in source


@pytest.mark.asyncio
async def test_bot_cleanup_is_idempotent():
    instance = TelegramChatBot.__new__(TelegramChatBot)
    instance._owns_service_container = True
    instance.message_dispatcher = SimpleNamespace(stop_dispatching=AsyncMock())
    instance.dispatcher_task = asyncio.create_task(asyncio.sleep(60))
    instance.service_container = SimpleNamespace(close=AsyncMock())
    instance._cleanup_lock = asyncio.Lock()
    instance._cleaned_up = False

    await instance.cleanup()
    await instance.cleanup()

    instance.message_dispatcher.stop_dispatching.assert_awaited_once()
    instance.service_container.close.assert_awaited_once()
