import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from message_manager import MessageDispatcher, MessageQueueManager
from bot_manager import BotManager


class ScriptRedis:
    def __init__(self):
        self.scripts = []
        self.rpush = AsyncMock(return_value=1)
        self.sadd = AsyncMock(return_value=1)

    def register_script(self, source):
        script = AsyncMock()
        script.source = source
        self.scripts.append(script)
        return script


@pytest.mark.asyncio
async def test_enqueue_atomically_publishes_all_parts_without_tokens():
    redis_client = ScriptRedis()
    with patch("message_manager.redis_async.from_url", return_value=redis_client):
        manager = MessageQueueManager("redis://user:secret@redis:6379/0")
    manager._split_message = Mock(return_value=["first", "second"])

    await manager.enqueue_message(
        user_id=7,
        chat_id=11,
        text="ignored",
        bot_id="bot-123",
    )

    manager.enqueue_script.assert_awaited_once()
    call = manager.enqueue_script.await_args
    assert call.kwargs["keys"] == ["queue:7:bot-123", "dispatcher:active_users"]
    assert call.kwargs["args"][0] == "7:bot-123"
    payloads = [json.loads(value) for value in call.kwargs["args"][1:]]
    assert [payload["text"] for payload in payloads] == ["first", "second"]
    assert all(payload["bot_id"] == "bot-123" for payload in payloads)
    assert all("bot_token" not in payload for payload in payloads)


@pytest.mark.asyncio
async def test_atomic_enqueue_failure_does_not_fall_back_to_partial_writes():
    redis_client = ScriptRedis()
    with patch("message_manager.redis_async.from_url", return_value=redis_client):
        manager = MessageQueueManager("redis://redis:6379/0")
    manager.enqueue_script.side_effect = RuntimeError("publication failed")

    with pytest.raises(RuntimeError, match="publication failed"):
        await manager.enqueue_message(user_id=7, chat_id=11, text="message")


@pytest.mark.asyncio
async def test_empty_queue_cleanup_uses_atomic_remove_script():
    redis_client = ScriptRedis()
    redis_client.blpop = AsyncMock(return_value=None)
    with patch("message_manager.redis_async.from_url", return_value=redis_client):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=AsyncMock())
    dispatcher.running = True
    dispatcher._renew_lock_periodically = AsyncMock()

    await dispatcher.process_user_queue(7, "bot-123")

    dispatcher.cleanup_route_script.assert_awaited_once_with(
        keys=["queue:7:bot-123", "dispatcher:active_users"],
        args=["7:bot-123"],
    )


@pytest.mark.asyncio
async def test_dispatcher_resolves_by_bot_id_once_and_reuses_client_for_parts():
    redis_client = ScriptRedis()
    resolver = SimpleNamespace(resolve=AsyncMock(return_value="resolved-token"))
    first_bot = SimpleNamespace(send_message=AsyncMock(), shutdown=AsyncMock())

    with (
        patch("message_manager.redis_async.from_url", return_value=redis_client),
        patch("message_manager.Bot", return_value=first_bot) as bot_class,
        patch("message_manager.send_ai_response", new=AsyncMock()),
    ):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=resolver)
        message = {
            "user_id": 7,
            "chat_id": 11,
            "text": "part",
            "message_type": "regular",
            "bot_id": "bot-123",
        }
        assert await dispatcher.process_message(dict(message)) is True
        assert await dispatcher.process_message(dict(message)) is True

    assert resolver.resolve.await_count == 2
    bot_class.assert_called_once_with(token="resolved-token")


@pytest.mark.asyncio
async def test_dispatcher_invalidation_closes_id_cached_client():
    redis_client = ScriptRedis()
    resolver = SimpleNamespace(resolve=AsyncMock(return_value="old-token"), invalidate=AsyncMock())
    bot = SimpleNamespace(shutdown=AsyncMock())
    with (
        patch("message_manager.redis_async.from_url", return_value=redis_client),
        patch("message_manager.Bot", return_value=bot),
        patch("message_manager.send_ai_response", new=AsyncMock()),
    ):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=resolver)
        await dispatcher.process_message(
            {"user_id": 7, "chat_id": 11, "text": "x", "message_type": "regular", "bot_id": "bot-123"}
        )
        await dispatcher.invalidate_bot("bot-123")

    resolver.invalidate.assert_awaited_once_with("bot-123")
    bot.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_bot_reload_invalidates_dispatcher_token_and_client_cache():
    bot_id = __import__("uuid").uuid4()
    manager = BotManager.__new__(BotManager)
    manager.bot_configs = {bot_id: SimpleNamespace(token="old", is_active=False)}
    manager.bots = {}
    manager._load_single_bot_config = AsyncMock()
    manager.service_container = SimpleNamespace(
        message_dispatcher=SimpleNamespace(invalidate_bot=AsyncMock())
    )

    await manager.reload_bot_config(bot_id)

    manager.service_container.message_dispatcher.invalidate_bot.assert_awaited_once_with(str(bot_id))


@pytest.mark.asyncio
async def test_unknown_bot_id_fails_without_using_legacy_token(caplog):
    redis_client = ScriptRedis()
    resolver = SimpleNamespace(resolve=AsyncMock(side_effect=LookupError("unknown bot")))
    with (
        patch("message_manager.redis_async.from_url", return_value=redis_client),
        patch("message_manager.Bot") as bot_class,
        caplog.at_level(logging.WARNING),
    ):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=resolver)
        ok = await dispatcher.process_message(
            {
                "user_id": 7,
                "chat_id": 11,
                "text": "x",
                "message_type": "regular",
                "bot_id": "unknown",
                "bot_token": "must-not-leak",
            }
        )

    assert ok is False
    bot_class.assert_not_called()
    assert "must-not-leak" not in caplog.text


@pytest.mark.asyncio
async def test_legacy_token_fallback_is_read_only_and_warning_is_token_free(caplog):
    redis_client = ScriptRedis()
    resolver = SimpleNamespace(resolve=AsyncMock(side_effect=LookupError("default unavailable")))
    legacy_bot = SimpleNamespace(shutdown=AsyncMock())
    legacy_message = {
        "user_id": 7,
        "chat_id": 11,
        "text": "x",
        "message_type": "regular",
        "bot_token": "legacy-secret",
    }
    with (
        patch("message_manager.redis_async.from_url", return_value=redis_client),
        patch("message_manager.Bot", return_value=legacy_bot),
        patch("message_manager.send_ai_response", new=AsyncMock()),
        caplog.at_level(logging.WARNING),
    ):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=resolver)
        assert await dispatcher.process_message(legacy_message) is True
        await dispatcher.handle_failed_message(legacy_message)

    assert "deprecated" in caplog.text.lower()
    assert "legacy-secret" not in caplog.text
    retried = json.loads(dispatcher.redis_client.rpush.await_args.args[1])
    assert "bot_token" not in retried
