"""Redis queue consumer that delivers messages to Telegram."""

import asyncio
import json
import logging
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, Any, Optional

import redis
import redis.asyncio as redis_async
from telegram import Bot
from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut

from settings import settings as app_settings

from messaging.queue import _await_redis
from messaging.sending import send_ai_response
from messaging.typing import TypingIndicatorManager

MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL = app_settings.queue.lock_refresh_interval
MESSAGE_QUEUE_DISPATCHER_INTERVAL = app_settings.queue.dispatcher_interval
TELEGRAM_TOKEN = app_settings.TELEGRAM_TOKEN

logger = logging.getLogger(__name__)


class MessageDispatcher:
    """Dispatches messages from Redis queues to send_ai_response function."""

    BOT_CACHE_MAX_SIZE = 50
    MAX_CONCURRENT_USERS = 20

    def __init__(self, redis_url: str, max_retries: int = 3, lock_timeout: int = 30, token_resolver=None):
        """
        Initialize the MessageDispatcher.

        Args:
            redis_url: Redis connection URL
            max_retries: Maximum number of retries for failed messages
            lock_timeout: Timeout for distributed locks in seconds
        """
        try:
            self.redis_client = redis_async.from_url(redis_url)
            self._closed = False
            logger.info("MessageDispatcher initialized")

            self.max_retries = max_retries
            self.lock_timeout = lock_timeout
            self.running = False
            self.max_concurrent_users = self.MAX_CONCURRENT_USERS

            # Telegram bots are created lazily and cached by token. This avoids
            # building an HTTP connection pool per message part.
            self.bot = None
            self._bot_cache: "OrderedDict[str, tuple[str, Bot]]" = OrderedDict()
            self.token_resolver = token_resolver
            self.typing_manager = TypingIndicatorManager()

            # Unique identifier for this dispatcher instance
            self.instance_id = str(uuid.uuid4())

            # Lua script for atomic lock acquisition
            self.lock_script = self.redis_client.register_script("""
            local lock_key = KEYS[1]
            local instance_id = ARGV[1]
            local lock_timeout = ARGV[2]

            -- Try to acquire the lock
            local result = redis.call('SET', lock_key, instance_id, 'NX', 'EX', lock_timeout)
            if result then
                return 1  -- Lock acquired
            else
                return 0  -- Lock not acquired
            end
            """)

            # Lua script for safe lock release (only release if owned by this instance)
            self.unlock_script = self.redis_client.register_script("""
            local lock_key = KEYS[1]
            local instance_id = ARGV[1]

            -- Get current lock owner
            local current_owner = redis.call('GET', lock_key)

            -- Only release if this instance owns the lock
            if current_owner == instance_id then
                redis.call('DEL', lock_key)
                return 1  -- Lock released
            else
                return 0  -- Lock not owned by this instance
            end
            """)

            # Lua script for lock renewal
            self.renew_script = self.redis_client.register_script("""
            local lock_key = KEYS[1]
            local instance_id = ARGV[1]
            local lock_timeout = ARGV[2]

            -- Get current lock owner
            local current_owner = redis.call('GET', lock_key)

            -- Only renew if this instance owns the lock
            if current_owner == instance_id then
                redis.call('EXPIRE', lock_key, lock_timeout)
                return 1  -- Lock renewed
            else
                return 0  -- Lock not owned by this instance
            end
            """)

            self.cleanup_route_script = self.redis_client.register_script("""
            local queue_key = KEYS[1]
            local active_routes_key = KEYS[2]
            local routing_key = ARGV[1]
            if redis.call('LLEN', queue_key) == 0 then
                return redis.call('SREM', active_routes_key, routing_key)
            end
            return 0
            """)

            # Requeue a failed message and (re)activate its route atomically so a
            # crash between the two operations can never orphan the message.
            self.requeue_script = self.redis_client.register_script("""
            local queue_key = KEYS[1]
            local active_routes_key = KEYS[2]
            local routing_key = ARGV[1]
            redis.call('RPUSH', queue_key, ARGV[2])
            redis.call('SADD', active_routes_key, routing_key)
            return 1
            """)

        except Exception as e:
            logger.error("Failed to initialize MessageDispatcher: %s", e)
            raise

    async def _get_bot_for_route(self, route_id: str, bot_token: str):
        """Return a client cached by route ID, replacing rotated credentials."""
        if not bot_token:
            return None

        cached = self._bot_cache.get(route_id)
        if cached is not None and cached[0] == bot_token:
            self._bot_cache.move_to_end(route_id)
            return cached[1]
        if cached is not None:
            await self._close_bot(cached[1])

        bot = Bot(token=bot_token)
        self._bot_cache[route_id] = (bot_token, bot)
        self._bot_cache.move_to_end(route_id)

        while len(self._bot_cache) > self.BOT_CACHE_MAX_SIZE:
            _, (_, evicted_bot) = self._bot_cache.popitem(last=False)
            await self._close_bot(evicted_bot)

        return bot

    @staticmethod
    async def _close_bot(bot) -> None:
        shutdown = getattr(bot, "shutdown", None)
        if shutdown:
            await shutdown()

    async def _resolve_token(self, bot_id: str | None) -> str:
        if self.token_resolver is None:
            if bot_id is not None or not TELEGRAM_TOKEN:
                raise LookupError("no token resolver is configured for this route")
            return TELEGRAM_TOKEN
        resolve = getattr(self.token_resolver, "resolve", self.token_resolver)
        return await resolve(bot_id)

    async def invalidate_bot(self, bot_id: str | None) -> None:
        route_id = bot_id or "default"
        if self.token_resolver is not None:
            invalidate = getattr(self.token_resolver, "invalidate", None)
            if invalidate:
                await invalidate(bot_id)
        cached = self._bot_cache.pop(route_id, None)
        if cached:
            await self._close_bot(cached[1])

    @staticmethod
    def _normalize_bot_key(bot_id: str = None) -> str:
        return bot_id or "default"

    @classmethod
    def _routing_key(cls, user_id: int, bot_id: str = None) -> str:
        return f"{user_id}:{cls._normalize_bot_key(bot_id)}"

    @classmethod
    def _queue_key(cls, user_id: int, bot_id: str = None) -> str:
        return f"queue:{cls._routing_key(user_id, bot_id)}"

    @classmethod
    def _dlq_key(cls, user_id: int, bot_id: str = None) -> str:
        return f"dlq:{cls._routing_key(user_id, bot_id)}"

    @classmethod
    def _lock_key(cls, user_id: int, bot_id: str = None) -> str:
        return f"dispatcher:processing:{cls._routing_key(user_id, bot_id)}"

    @staticmethod
    def _parse_routing_key(raw_routing_key) -> tuple[int, Optional[str]]:
        routing_key = raw_routing_key.decode('utf-8') if isinstance(raw_routing_key, bytes) else raw_routing_key
        routing_parts = routing_key.split(":", 1)
        user_id = int(routing_parts[0])
        bot_id = routing_parts[1] if len(routing_parts) > 1 and routing_parts[1] != "default" else None
        return user_id, bot_id

    async def _process_active_routing_key(self, raw_routing_key, semaphore: asyncio.Semaphore):
        async with semaphore:
            try:
                user_id, bot_id = self._parse_routing_key(raw_routing_key)
            except (ValueError, AttributeError):
                logger.warning("Invalid user ID in active users set: %s", raw_routing_key)
                return

            lock_acquired = await _await_redis(self.acquire_lock(user_id, bot_id))

            if not lock_acquired:
                return

            try:
                await self.process_user_queue(user_id, bot_id)
            except Exception as e:
                logger.error("Error processing queue for user %s bot %s: %s", user_id, bot_id, e)
            finally:
                await _await_redis(self.release_lock(user_id, bot_id))

    async def _process_active_users(self, active_users):
        semaphore = asyncio.Semaphore(self.max_concurrent_users)
        tasks = [
            asyncio.create_task(self._process_active_routing_key(active_user, semaphore))
            for active_user in active_users
        ]
        if tasks:
            await asyncio.gather(*tasks)

    async def acquire_lock(self, user_id: int, bot_id: str = None) -> bool:
        """
        Acquire a distributed lock for a user queue.

        Args:
            user_id: User ID

        Returns:
            True if lock was acquired, False otherwise
        """
        try:
            lock_key = self._lock_key(user_id, bot_id)
            result = await _await_redis(self.lock_script(
                keys=[lock_key],
                args=[self.instance_id, self.lock_timeout]
            ))
            lock_acquired = bool(result)

            if lock_acquired:
                logger.debug("Acquired lock for user %s (instance: %s)", user_id, self.instance_id)
            else:
                logger.debug("Failed to acquire lock for user %s (instance: %s)", user_id, self.instance_id)

            return lock_acquired
        except Exception as e:
            logger.error("Error acquiring lock for user %s: %s", user_id, e)
            return False

    async def release_lock(self, user_id: int, bot_id: str = None) -> bool:
        """
        Release a distributed lock for a user queue.

        Args:
            user_id: User ID

        Returns:
            True if lock was released, False otherwise
        """
        try:
            lock_key = self._lock_key(user_id, bot_id)
            result = await _await_redis(self.unlock_script(
                keys=[lock_key],
                args=[self.instance_id]
            ))
            lock_released = bool(result)

            if lock_released:
                logger.debug("Released lock for user %s (instance: %s)", user_id, self.instance_id)
            else:
                logger.debug("Failed to release lock for user %s (instance: %s) - not owned by this instance", user_id, self.instance_id)

            return lock_released
        except Exception as e:
            logger.error("Error releasing lock for user %s: %s", user_id, e)
            return False

    async def renew_lock(self, user_id: int, bot_id: str = None) -> bool:
        """
        Renew a distributed lock for a user queue.

        Args:
            user_id: User ID

        Returns:
            True if lock was renewed, False otherwise
        """
        try:
            lock_key = self._lock_key(user_id, bot_id)
            result = await _await_redis(self.renew_script(
                keys=[lock_key],
                args=[self.instance_id, self.lock_timeout]
            ))
            lock_renewed = bool(result)

            if lock_renewed:
                logger.debug("Renewed lock for user %s (instance: %s)", user_id, self.instance_id)
            else:
                logger.debug("Failed to renew lock for user %s (instance: %s) - not owned by this instance", user_id, self.instance_id)

            return lock_renewed
        except Exception as e:
            logger.error("Error renewing lock for user %s: %s", user_id, e)
            return False

    async def _scan_existing_queues(self):
        """
        Scan Redis for existing user queues and add them to the active users set.
        This ensures that queued messages from previous runs are processed.
        """
        try:
            logger.info("Starting scan for existing queues...")
            # Scan for keys matching the pattern "queue:*"
            pattern = "queue:*"
            cursor = 0
            scanned_count = 0
            added_count = 0

            while True:
                cursor, keys = await _await_redis(self.redis_client.scan(cursor=cursor, match=pattern))
                scanned_count += len(keys)

                # Add users with non-empty queues to the active users set
                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str.startswith("queue:"):
                        try:
                            key_parts = key_str.split(":")
                            if len(key_parts) == 2:
                                user_id = int(key_parts[1])
                                routing_key = self._routing_key(user_id)
                            elif len(key_parts) == 3:
                                user_id = int(key_parts[1])
                                routing_key = f"{key_parts[1]}:{key_parts[2]}"
                            else:
                                logger.warning("Invalid queue key format: %s", key_str)
                                continue
                            queue_size = await _await_redis(self.redis_client.llen(key_str))
                            if queue_size > 0:
                                await _await_redis(self.redis_client.sadd("dispatcher:active_users", routing_key))
                                logger.info("Found existing queue for routing key %s with %s messages", routing_key, queue_size)
                                added_count += 1
                            else:
                                logger.debug("Found empty queue for routing key %s", routing_key)
                        except (ValueError, IndexError):
                            logger.warning("Invalid queue key format: %s", key_str)
                        except redis.RedisError as e:
                            logger.error("Redis error while processing queue %s: %s", key_str, e)
                        except Exception as e:
                            logger.error("Unexpected error while processing queue %s: %s", key_str, e)

                # Exit if we've scanned all keys
                if cursor == 0:
                    break

            logger.info("Finished scanning for existing queues. Scanned %s keys, added %s users to active set", scanned_count, added_count)
        except redis.RedisError as e:
            logger.error("Redis error while scanning existing queues: %s", e)
        except Exception as e:
            logger.error("Unexpected error while scanning existing queues: %s", e)

    async def start_dispatching(self):
        """Start the dispatcher loop."""
        logger.info("Starting message dispatcher")
        self.running = True
        try:
            # Scan for existing queues at startup
            await self._scan_existing_queues()

            while self.running:
                try:
                    # Get set of active users
                    active_users = await _await_redis(self.redis_client.smembers("dispatcher:active_users"))

                    if not active_users:
                        # No active users, sleep for a bit
                        await asyncio.sleep(MESSAGE_QUEUE_DISPATCHER_INTERVAL)
                        continue

                    await self._process_active_users(active_users)

                    # Sleep for a bit before checking again
                    await asyncio.sleep(MESSAGE_QUEUE_DISPATCHER_INTERVAL)

                except redis.RedisError as e:
                    logger.error("Redis error in dispatcher loop: %s", e)
                    # Don't let one error stop the entire dispatcher
                    await asyncio.sleep(MESSAGE_QUEUE_DISPATCHER_INTERVAL)
                except Exception as e:
                    logger.error("Error in dispatcher loop: %s", e)
                    # Don't let one error stop the entire dispatcher
                    await asyncio.sleep(MESSAGE_QUEUE_DISPATCHER_INTERVAL)

        except asyncio.CancelledError:
            logger.info("Message dispatcher cancelled")
        except redis.RedisError as e:
            logger.error("Redis error in message dispatcher: %s", e)
        except Exception as e:
            logger.error("Fatal error in message dispatcher: %s", e)
        finally:
            self.running = False
            logger.info("Message dispatcher stopped")

    async def stop_dispatching(self):
        """Stop the dispatcher loop."""
        logger.info("Stopping message dispatcher")
        self.running = False

    async def close(self) -> None:
        """Stop dispatching and release Telegram and Redis clients exactly once."""
        if self._closed:
            return
        self._closed = True
        await self.stop_dispatching()
        await self.typing_manager.cleanup()
        cached_bots = [cached[1] for cached in self._bot_cache.values()]
        self._bot_cache.clear()
        for bot in cached_bots:
            await self._close_bot(bot)
        await self.redis_client.aclose()

    async def process_user_queue(self, user_id: int, bot_id: str = None):
        """
        Process messages from a user's queue.

        Args:
            user_id: User ID
        """
        # Create a task for lock renewal
        lock_lost_event = asyncio.Event()
        lock_renewal_task = asyncio.create_task(self._renew_lock_periodically(user_id, bot_id, lock_lost_event))

        try:
            queue_key = self._queue_key(user_id, bot_id)
            routing_key = self._routing_key(user_id, bot_id)
            logger.info("Starting to process queue for user %s bot %s", user_id, bot_id)

            # Process all messages in the queue
            message_count = 0
            while self.running:
                if lock_lost_event.is_set():
                    logger.warning("Stopping queue processing for user %s bot %s because dispatcher lock was lost", user_id, bot_id)
                    break

                try:
                    # BLPOP blocks until a message is available or times out
                    result = await _await_redis(self.redis_client.blpop([queue_key], timeout=1))
                except redis.RedisError as e:
                    logger.error("Redis error while fetching message from queue for user %s: %s", user_id, e)
                    # Continue with the loop to retry
                    await asyncio.sleep(0.1)
                    continue

                if not result:
                    # No more messages in queue, remove user from active set
                    try:
                        await _await_redis(self.cleanup_route_script(
                            keys=[queue_key, "dispatcher:active_users"],
                            args=[routing_key],
                        ))
                        logger.info("Finished processing queue for user %s bot %s. Processed %s messages", user_id, bot_id, message_count)
                    except redis.RedisError as e:
                        logger.error("Redis error while removing user %s bot %s from active set: %s", user_id, bot_id, e)
                    break

                # Extract message
                _, message_json = result
                try:
                    message_data = json.loads(message_json.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError) as e:
                    logger.error("Failed to decode message for user %s: %s", user_id, e)
                    continue
                except Exception as e:
                    logger.error("Unexpected error while decoding message for user %s: %s", user_id, e)
                    continue

                message_count += 1
                logger.debug("Processing message %s for user %s", message_count, user_id)

                # Process the message
                try:
                    success = await self.process_message(message_data)
                except Exception as e:
                    logger.error("Error processing message for user %s: %s", user_id, e)
                    success = False

                if not success:
                    # Handle failed message
                    try:
                        await self.handle_failed_message(message_data)
                    except Exception as e:
                        logger.error("Error handling failed message for user %s: %s", user_id, e)

        except redis.RedisError as e:
            logger.error("Redis error processing queue for user %s bot %s: %s", user_id, bot_id, e)
        except Exception as e:
            logger.error("Error processing queue for user %s bot %s: %s", user_id, bot_id, e)
        finally:
            # Cancel the lock renewal task
            lock_renewal_task.cancel()
            try:
                await lock_renewal_task
            except asyncio.CancelledError:
                pass

    async def _renew_lock_periodically(self, user_id: int, bot_id: str = None, lock_lost_event: asyncio.Event = None):
        """
        Periodically renew the lock for a user queue.

        Args:
            user_id: User ID
        """
        try:
            while True:
                await asyncio.sleep(MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL)
                lock_renewed = await _await_redis(self.renew_lock(user_id, bot_id))
                if not lock_renewed:
                    logger.warning("Failed to renew lock for user %s bot %s", user_id, bot_id)
                    if lock_lost_event:
                        lock_lost_event.set()
                    # If we can't renew the lock, we should stop processing
                    break
        except asyncio.CancelledError:
            # Task was cancelled, which is expected when processing is done
            pass
        except Exception as e:
            logger.error("Error in lock renewal task for user %s bot %s: %s", user_id, bot_id, e)
            if lock_lost_event:
                lock_lost_event.set()

    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single message part.

        Args:
            message: Message data dictionary

        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate message structure
            required_fields = ["user_id", "chat_id", "text", "message_type"]
            for field in required_fields:
                if field not in message:
                    logger.error("Missing required field '%s' in queued message", field)
                    return False

            user_id = message["user_id"]
            chat_id = message["chat_id"]
            text = message["text"]
            message_type = message["message_type"]
            retry_count = message.get("retry_count", 0)
            part_index = message.get("part_index", 0)
            total_parts = message.get("total_parts", 1)

            # Validate field types
            if not isinstance(user_id, int) or user_id <= 0:
                logger.error("Invalid user_id in message: %s", user_id)
                return False

            if not isinstance(chat_id, int):
                logger.error("Invalid chat_id in message: %s", chat_id)
                return False

            if not isinstance(text, str) or not text:
                logger.error("Invalid text in queued message")
                return False

            if message_type not in ["regular", "proactive"]:
                logger.error("Invalid message_type in message: %s", message_type)
                return False

            logger.info("Processing message part %d/%d for user %s (chat %s) of type %s, retry count: %s",
                       part_index + 1, total_parts, user_id, chat_id, message_type, retry_count)

            # Determine if this is the first message part in a sequence (no delay before first)
            is_first_message = (part_index == 0)

            # Send the message part
            try:
                bot_to_use = None
                bot_id = message.get("bot_id")
                route_id = str(bot_id) if bot_id else "default"
                try:
                    bot_token = await self._resolve_token(str(bot_id) if bot_id else None)
                except LookupError:
                    legacy_token = message.get("bot_token") if bot_id is None else None
                    if not legacy_token:
                        logger.warning("Unable to resolve Telegram credentials for route %s", route_id)
                        return False
                    logger.warning("Using deprecated token-bearing legacy queue payload for default route")
                    bot_token = legacy_token
                try:
                    bot_to_use = await self._get_bot_for_route(route_id, bot_token)
                except Exception as e:
                    logger.error("Failed to create bot instance for route %s: %s", route_id, e)
                    return False

                if not bot_to_use:
                    logger.error("No bot instance available to send message for user %s", user_id)
                    return False

                await send_ai_response(
                    chat_id=chat_id,
                    text=text,
                    bot=bot_to_use,
                    typing_manager=self.typing_manager,
                    is_first_message=is_first_message,
                    route_key=self._routing_key(user_id, message.get("bot_id"))
                )

            # NOTE on ordering: in python-telegram-bot ``BadRequest`` and
            # ``TimedOut`` are both subclasses of ``NetworkError``, so the
            # deterministic ``BadRequest`` handler must precede the transient
            # ``(TimedOut, NetworkError)`` handler, otherwise a 4xx would be
            # retried. ``RetryAfter`` and ``Forbidden`` are independent.
            except RetryAfter as e:
                # Telegram flood control. This is backpressure, not a delivery
                # failure: wait out the window it asks for, then requeue the part
                # without spending a retry so genuine failures still hit max_retries.
                delay = int(getattr(e, "retry_after", 0)) + 1
                logger.warning(
                    "Flood control while sending to user %s; retrying after %ss", user_id, delay
                )
                await asyncio.sleep(delay)
                await self._requeue_without_retry(message)
                return True

            except BadRequest as e:
                # A 4xx from Telegram is deterministic; retrying cannot help.
                error_msg = str(e).lower()
                if "chat not found" in error_msg or "user is deactivated" in error_msg or "bot was blocked" in error_msg:
                    logger.warning(
                        "Permanent delivery error for user %s (%s); disabling proactive messaging", user_id, e
                    )
                    try:
                        await self._disable_proactive_messaging_for_user(user_id, bot_id=message.get("bot_id"))
                    except Exception as disable_error:
                        logger.error("Failed to disable proactive messaging for user %s: %s", user_id, disable_error)
                else:
                    logger.warning(
                        "Non-retryable error sending message part %d/%d for user %s: %s; dropping message",
                        part_index + 1, total_parts, user_id, e,
                    )
                return True

            except Forbidden as e:
                # The user blocked the bot or the chat is gone. Deterministic: do
                # not retry. Drop the message and stop proactive outreach.
                logger.warning(
                    "User %s is unreachable (%s); dropping message and disabling proactive messaging",
                    user_id, e,
                )
                try:
                    await self._disable_proactive_messaging_for_user(user_id, bot_id=message.get("bot_id"))
                except Exception as disable_error:
                    logger.error("Failed to disable proactive messaging for user %s: %s", user_id, disable_error)
                return True

            except (TimedOut, NetworkError) as e:
                # Transient network failure. Back off with a bounded exponential
                # delay before the normal retry path requeues and increments the
                # retry count. The per-user task isolates this sleep from other users.
                backoff = min(2 ** retry_count, 30)
                logger.warning(
                    "Transient network error (%s) sending to user %s; backing off %ss before retry",
                    type(e).__name__, user_id, backoff,
                )
                await asyncio.sleep(backoff)
                return False

            logger.info("Successfully processed message part %d/%d for user %s", part_index + 1, total_parts, user_id)
            return True

        except Exception as e:
            logger.error("Error processing message: %s", e)
            return False

    async def _requeue_without_retry(self, message: Dict[str, Any]) -> None:
        """Requeue a message and reactivate its route without spending a retry.

        Used for Telegram flood control (RetryAfter): the send did not fail, we
        were merely asked to slow down, so the retry budget must not be consumed.
        Token-bearing fields are stripped for the same reason as handle_failed_message.
        """
        user_id = message["user_id"]
        bot_id = message.get("bot_id")
        safe_message = {key: value for key, value in message.items() if key not in {"bot_token", "token"}}
        message_json = json.dumps(safe_message, ensure_ascii=False)
        await _await_redis(self.requeue_script(
            keys=[self._queue_key(user_id, bot_id), "dispatcher:active_users"],
            args=[self._routing_key(user_id, bot_id), message_json],
        ))

    async def handle_failed_message(self, message: Dict[str, Any]):
        """
        Handle a failed message.

        Args:
            message: Message data dictionary
        """
        try:
            user_id = message["user_id"]
            bot_id = message.get("bot_id")
            retry_count = message.get("retry_count", 0)
            safe_message = {key: value for key, value in message.items() if key not in {"bot_token", "token"}}

            if retry_count < self.max_retries:
                # Increment retry count and requeue atomically with route activation.
                safe_message["retry_count"] = retry_count + 1
                message_json = json.dumps(safe_message, ensure_ascii=False)
                await _await_redis(self.requeue_script(
                    keys=[self._queue_key(user_id, bot_id), "dispatcher:active_users"],
                    args=[self._routing_key(user_id, bot_id), message_json],
                ))
                logger.info("Requeued failed message for user %s bot %s (retry %s)", user_id, bot_id, retry_count + 1)
            else:
                # Move to dead letter queue
                dlq_key = self._dlq_key(user_id, bot_id)
                message_json = json.dumps(safe_message, ensure_ascii=False)
                await _await_redis(self.redis_client.rpush(dlq_key, message_json))
                logger.error("Moved message to dead letter queue for user %s bot %s after %s retries", user_id, bot_id, self.max_retries)

        except Exception as e:
            logger.error("Error handling failed message for user %s: %s", message.get("user_id", "unknown"), e)

    async def _disable_proactive_messaging_for_user(self, user_id: int, bot_id: str = None):
        """Disable proactive messaging for a user due to permanent error (blocked/chat not found)."""
        try:
            state_key = f"proactive_messaging:user:{user_id}:{bot_id or 'default'}"
            state_json = await _await_redis(self.redis_client.get(state_key))
            if state_json:
                state = json.loads(state_json)
                state['is_active'] = False
                state['last_error'] = "Permanent failure (Chat not found / Forbidden)"
                state['error_time'] = datetime.now(timezone.utc).isoformat()
                await _await_redis(self.redis_client.set(state_key, json.dumps(state, default=str)))
                logger.info("Proactive messaging disabled for user %s bot %s in Redis", user_id, bot_id)
            else:
                # Create a minimal state to mark as inactive
                state = {
                    'is_active': False,
                    'user_id': user_id,
                    'bot_id': bot_id,
                    'last_error': "Permanent failure (Chat not found / Forbidden)",
                    'error_time': datetime.now(timezone.utc).isoformat()
                }
                await _await_redis(self.redis_client.set(state_key, json.dumps(state, default=str)))
                logger.info("Created inactive state for user %s bot %s in Redis", user_id, bot_id)
        except Exception as e:
            logger.error("Error while trying to disable proactive messaging in Redis for user %s bot %s: %s", user_id, bot_id, e)
