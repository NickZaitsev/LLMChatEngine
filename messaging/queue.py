"""Redis-backed per-route message queueing."""

import inspect
import json
import logging
from datetime import datetime, timezone, UTC

import redis
import redis.asyncio as redis_async

from messaging.formatting import _split_ai_response

logger = logging.getLogger(__name__)


async def _await_redis(value):
    """Await a redis result when the client is async, else return it directly."""
    return await value if inspect.isawaitable(value) else value


class MessageQueueManager:
    """Manages message queuing to Redis lists per user to prevent parallel execution of send_ai_response."""

    def __init__(self, redis_url: str):
        """
        Initialize the MessageQueueManager.

        Args:
            redis_url: Redis connection URL
        """
        try:
            self.redis_client = redis_async.from_url(redis_url)
            self._closed = False
            self.enqueue_script = self.redis_client.register_script("""
            local queue_key = KEYS[1]
            local active_routes_key = KEYS[2]
            local routing_key = ARGV[1]
            for index = 2, #ARGV do
                redis.call('RPUSH', queue_key, ARGV[index])
            end
            redis.call('SADD', active_routes_key, routing_key)
            return #ARGV - 1
            """)
            logger.info("MessageQueueManager initialized")
        except Exception as e:
            logger.error("Failed to initialize MessageQueueManager: %s", e)
            raise

    async def close(self) -> None:
        """Close the owned Redis client exactly once."""
        if self._closed:
            return
        self._closed = True
        await self.redis_client.aclose()

    @staticmethod
    def _normalize_bot_key(bot_id: str | None = None) -> str:
        return bot_id or "default"

    @classmethod
    def _routing_key(cls, user_id: int, bot_id: str | None = None) -> str:
        return f"{user_id}:{cls._normalize_bot_key(bot_id)}"

    @classmethod
    def _queue_key(cls, user_id: int, bot_id: str | None = None) -> str:
        return f"queue:{cls._routing_key(user_id, bot_id)}"

    def _split_message(self, text: str) -> list:
        """
        Split a message into safe parts before queuing to maintain order.

        Args:
            text: Message text to split

        Returns:
            List of message parts
        """
        return _split_ai_response(text)

    async def enqueue_message(self, user_id: int, chat_id: int, text: str, message_type: str = "regular", bot_id: str | None = None):
        """
        Enqueue a message for a user in their Redis list. If the message needs to be split,
        split it first and enqueue each part as a separate message to maintain order.

        Args:
            user_id: User ID
            chat_id: Chat ID
            text: Message text
            message_type: Type of message ("regular" or "proactive")
            bot_id: Optional bot ID for multi-bot proactive state routing
        """
        try:
            # Validate inputs
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("user_id must be a positive integer")

            if not isinstance(chat_id, int):
                raise ValueError("chat_id must be an integer")

            if not text or not isinstance(text, str):
                raise ValueError("text must be a non-empty string")

            if message_type not in ["regular", "proactive"]:
                raise ValueError("message_type must be 'regular' or 'proactive'")

            # Split the message before queuing to maintain order
            message_parts = self._split_message(text)

            # If there are no parts to send, return early
            if not message_parts:
                logger.warning("No message parts to enqueue for user %s", user_id)
                return

            routing_key = self._routing_key(user_id, bot_id)
            total_parts = len(message_parts)
            serialized_parts = []
            for i, part_text in enumerate(message_parts):
                # Create message payload for this part
                message_data = {
                    "user_id": user_id,
                    "chat_id": chat_id,
                    "text": part_text,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "message_type": message_type,
                    "retry_count": 0,
                    "part_index": i,
                    "total_parts": total_parts,
                    "bot_id": bot_id,
                }
                serialized_parts.append(json.dumps(message_data, ensure_ascii=False))

            queue_key = self._queue_key(user_id, bot_id)
            await _await_redis(self.enqueue_script(
                keys=[queue_key, "dispatcher:active_users"],
                args=[routing_key, *serialized_parts],
            ))
            logger.info(
                "Atomically enqueued %d message parts for user %s (chat %s) of type %s",
                total_parts, user_id, chat_id, message_type,
            )

        except ValueError as e:
            logger.error("Validation error when enqueuing message for user %s: %s", user_id, e)
            raise
        except redis.RedisError as e:
            logger.error("Redis error when enqueuing message for user %s: %s", user_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error when enqueuing message for user %s: %s", user_id, e)
            raise

    async def get_queue_size(self, user_id: int, bot_id: str | None = None) -> int:
        """
        Get the size of a user's queue.

        Args:
            user_id: User ID

        Returns:
            Number of messages in the queue
        """
        try:
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("user_id must be a positive integer")

            queue_key = self._queue_key(user_id, bot_id)
            size = await _await_redis(self.redis_client.llen(queue_key))
            return size
        except ValueError as e:
            logger.error("Validation error when getting queue size for user %s: %s", user_id, e)
            raise
        except redis.RedisError as e:
            logger.error("Redis error when getting queue size for user %s: %s", user_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error when getting queue size for user %s: %s", user_id, e)
            raise

    async def is_queue_empty(self, user_id: int, bot_id: str | None = None) -> bool:
        """
        Check if a user's queue is empty.

        Args:
            user_id: User ID

        Returns:
            True if queue is empty, False otherwise
        """
        try:
            size = await self.get_queue_size(user_id, bot_id)
            return size == 0
        except Exception as e:
            logger.error("Error when checking if queue is empty for user %s: %s", user_id, e)
            raise
