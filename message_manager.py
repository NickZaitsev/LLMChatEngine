"""Compatibility re-export shim for the messaging package.

The implementation now lives in the ``messaging`` package. New code should import
from ``messaging.formatting`` / ``messaging.typing`` / ``messaging.queue`` /
``messaging.dispatcher`` / ``messaging.sending`` directly. This module keeps the
historical ``message_manager`` import surface working for one release.
"""

# Kept importable so legacy ``patch("message_manager.redis_async.from_url")``
# and ``import redis`` targets continue to resolve.
import redis  # noqa: F401
import redis.asyncio as redis_async  # noqa: F401
from telegram import Bot  # noqa: F401

from messaging.formatting import clean_ai_response, _split_ai_response
from messaging.typing import TypingIndicatorManager
from messaging.queue import MessageQueueManager, _await_redis
from messaging.dispatcher import (
    MessageDispatcher,
    TELEGRAM_TOKEN,
    MESSAGE_QUEUE_DISPATCHER_INTERVAL,
    MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL,
)
from messaging.sending import (
    send_ai_response,
    generate_ai_response,
    MIN_TYPING_SPEED,
    MAX_TYPING_SPEED,
    MAX_DELAY,
    RANDOM_OFFSET_MIN,
    RANDOM_OFFSET_MAX,
)

__all__ = [
    "clean_ai_response",
    "_split_ai_response",
    "TypingIndicatorManager",
    "MessageQueueManager",
    "MessageDispatcher",
    "send_ai_response",
    "generate_ai_response",
    "_await_redis",
    "Bot",
    "redis",
    "redis_async",
    "TELEGRAM_TOKEN",
    "MIN_TYPING_SPEED",
    "MAX_TYPING_SPEED",
    "MAX_DELAY",
    "RANDOM_OFFSET_MIN",
    "RANDOM_OFFSET_MAX",
    "MESSAGE_QUEUE_DISPATCHER_INTERVAL",
    "MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL",
]
