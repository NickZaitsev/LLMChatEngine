"""Delivery-resilience behaviour of MessageDispatcher.process_message.

Covers Telegram flood control (RetryAfter), transient network errors
(TimedOut / NetworkError) and deterministic 4xx errors (Forbidden / BadRequest).
No real network calls or real sleeps happen: the Telegram client and
``asyncio.sleep`` are mocked.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from messaging.dispatcher import MessageDispatcher


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


def _message(**overrides):
    message = {
        "user_id": 7,
        "chat_id": 11,
        "text": "hello",
        "message_type": "regular",
        "bot_id": "bot-1",
        "retry_count": 0,
    }
    message.update(overrides)
    return message


def _build_dispatcher(redis_client, send_side_effect):
    resolver = SimpleNamespace(resolve=AsyncMock(return_value="token"))
    bot = SimpleNamespace(shutdown=AsyncMock())
    ctx = (
        patch("messaging.dispatcher.redis_async.from_url", return_value=redis_client),
        patch("messaging.dispatcher.Bot", return_value=bot),
        patch("messaging.dispatcher.send_ai_response", new=AsyncMock(side_effect=send_side_effect)),
    )
    return resolver, ctx


@pytest.mark.asyncio
async def test_retry_after_sleeps_and_requeues_without_incrementing():
    redis_client = ScriptRedis()
    sleep_mock = AsyncMock()
    _, (p_redis, p_bot, p_send) = _build_dispatcher(redis_client, RetryAfter(5))
    with p_redis, p_bot, p_send, patch("messaging.dispatcher.asyncio.sleep", sleep_mock):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=SimpleNamespace(resolve=AsyncMock(return_value="token")))
        result = await dispatcher.process_message(_message(retry_count=2))

    assert result is True  # handled, so no extra retry is spent by the caller
    sleep_mock.assert_awaited_once_with(6)  # retry_after + 1
    dispatcher.requeue_script.assert_awaited_once()
    requeued = json.loads(dispatcher.requeue_script.await_args.kwargs["args"][1])
    assert requeued["retry_count"] == 2  # unchanged: flood control is not a failure


@pytest.mark.asyncio
async def test_forbidden_drops_message_without_requeue():
    redis_client = ScriptRedis()
    _, (p_redis, p_bot, p_send) = _build_dispatcher(redis_client, Forbidden("bot was blocked by the user"))
    with p_redis, p_bot, p_send:
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=SimpleNamespace(resolve=AsyncMock(return_value="token")))
        dispatcher._disable_proactive_messaging_for_user = AsyncMock()
        result = await dispatcher.process_message(_message())

    assert result is True  # dropped, not retried
    dispatcher.requeue_script.assert_not_awaited()
    dispatcher._disable_proactive_messaging_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_bad_request_drops_message_without_requeue():
    redis_client = ScriptRedis()
    _, (p_redis, p_bot, p_send) = _build_dispatcher(redis_client, BadRequest("message text is empty"))
    with p_redis, p_bot, p_send:
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=SimpleNamespace(resolve=AsyncMock(return_value="token")))
        result = await dispatcher.process_message(_message())

    assert result is True  # deterministic 4xx: dropped, not retried
    dispatcher.requeue_script.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimedOut(), NetworkError("connection reset")])
async def test_transient_error_backs_off_then_signals_retry(error):
    redis_client = ScriptRedis()
    sleep_mock = AsyncMock()
    _, (p_redis, p_bot, p_send) = _build_dispatcher(redis_client, error)
    with p_redis, p_bot, p_send, patch("messaging.dispatcher.asyncio.sleep", sleep_mock):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=SimpleNamespace(resolve=AsyncMock(return_value="token")))
        result = await dispatcher.process_message(_message(retry_count=3))

    assert result is False  # let the normal retry path increment and requeue
    sleep_mock.assert_awaited_once_with(8)  # min(2 ** 3, 30)
    dispatcher.requeue_script.assert_not_awaited()  # requeue happens in handle_failed_message


@pytest.mark.asyncio
async def test_transient_backoff_is_capped_at_thirty_seconds():
    redis_client = ScriptRedis()
    sleep_mock = AsyncMock()
    _, (p_redis, p_bot, p_send) = _build_dispatcher(redis_client, NetworkError("boom"))
    with p_redis, p_bot, p_send, patch("messaging.dispatcher.asyncio.sleep", sleep_mock):
        dispatcher = MessageDispatcher("redis://redis:6379/0", token_resolver=SimpleNamespace(resolve=AsyncMock(return_value="token")))
        await dispatcher.process_message(_message(retry_count=10))

    sleep_mock.assert_awaited_once_with(30)


@pytest.mark.asyncio
async def test_transient_failure_moves_to_dlq_after_max_retries():
    redis_client = ScriptRedis()
    with patch("messaging.dispatcher.redis_async.from_url", return_value=redis_client):
        dispatcher = MessageDispatcher("redis://redis:6379/0", max_retries=3, token_resolver=AsyncMock())

    # retry_count already at max_retries -> should go to the dead letter queue.
    await dispatcher.handle_failed_message(_message(retry_count=3))

    dispatcher.requeue_script.assert_not_awaited()
    redis_client.rpush.assert_awaited_once()
    dlq_key = redis_client.rpush.await_args.args[0]
    assert dlq_key == "dlq:7:bot-1"
