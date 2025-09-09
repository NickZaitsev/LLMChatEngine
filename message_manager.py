import asyncio
import logging
import random
import time
import json
import redis
import uuid
from datetime import datetime
from config import MIN_TYPING_SPEED, MAX_TYPING_SPEED, MAX_DELAY, RANDOM_OFFSET_MIN, RANDOM_OFFSET_MAX, MESSAGE_QUEUE_MAX_RETRIES, MESSAGE_QUEUE_LOCK_TIMEOUT, MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL, MESSAGE_QUEUE_DISPATCHER_INTERVAL
import textwrap
import re
from typing import Dict, Set, Optional, Any
from telegram import Bot
from config import TELEGRAM_TOKEN

logger = logging.getLogger(__name__)

def clean_ai_response(text: str) -> str:
    """
    Clean and normalize text by:
    - Stripping leading/trailing whitespace
    - Reducing multiple consecutive newlines to double newlines
    - Removing leading/trailing whitespace from each line
    """
    text = text.strip()
    
    # Reduce multiple consecutive newlines to double newlines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove leading/trailing whitespace from each line
    lines = text.split('\n')
    cleaned_lines = [line.strip() for line in lines]
    text = '\n'.join(cleaned_lines)

    # Additional cleanup for cases with remaining whitespace
    text = re.sub(r'\n{2,}\.\.\.', '\n\n', text)
    
    return text


class TypingIndicatorManager:
    """Manages typing indicators for concurrent conversations"""
    
    def __init__(self):
        self._active_typing_tasks: Dict[int, asyncio.Task] = {}
        self._typing_locks: Dict[int, asyncio.Lock] = {}
        self.typing_interval = 3.0  # Send typing action every 3 seconds
    
    async def start_typing(self, bot: Bot, chat_id: int) -> None:
        """Start typing indicator for a specific chat"""
        try:
            # Cancel any existing typing task for this chat
            await self.stop_typing(chat_id)
            
            # Create lock for this chat if it doesn't exist
            if chat_id not in self._typing_locks:
                self._typing_locks[chat_id] = asyncio.Lock()
            
            async with self._typing_locks[chat_id]:
                # Create and start new typing task
                task = asyncio.create_task(
                    self._typing_loop(bot, chat_id),
                    name=f"typing_indicator_{chat_id}"
                )
                self._active_typing_tasks[chat_id] = task
                logger.debug("Started typing indicator for chat %s", chat_id)
                
        except Exception as e:
            logger.error("Failed to start typing indicator for chat %s: %s", chat_id, e)
    
    async def stop_typing(self, chat_id: int) -> None:
        """Stop typing indicator for a specific chat"""
        try:
            if chat_id in self._active_typing_tasks:
                task = self._active_typing_tasks[chat_id]
                if not task.done():
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                del self._active_typing_tasks[chat_id]
                logger.debug("Stopped typing indicator for chat %s", chat_id)
                
        except Exception as e:
            logger.error("Failed to stop typing indicator for chat %s: %s", chat_id, e)
    
    async def stop_all_typing(self) -> None:
        """Stop all active typing indicators"""
        chat_ids = list(self._active_typing_tasks.keys())
        for chat_id in chat_ids:
            await self.stop_typing(chat_id)
    
    async def _typing_loop(self, bot: Bot, chat_id: int) -> None:
        """Internal loop that sends typing action every 3 seconds"""
        try:
            while True:
                try:
                    await bot.send_chat_action(chat_id=chat_id, action="typing")
                    logger.debug("Sent typing action to chat %s", chat_id)
                except Exception as e:
                    logger.warning("Failed to send typing action to chat %s: %s", chat_id, e)
                    # Continue loop despite individual failures
                
                # Wait for next typing interval
                await asyncio.sleep(self.typing_interval)
                
        except asyncio.CancelledError:
            logger.debug("Typing loop cancelled for chat %s", chat_id)
            raise
        except Exception as e:
            logger.error("Unexpected error in typing loop for chat %s: %s", chat_id, e)
    
    def is_typing_active(self, chat_id: int) -> bool:
        """Check if typing is currently active for a chat"""
        return (chat_id in self._active_typing_tasks and 
                not self._active_typing_tasks[chat_id].done())
    
    def get_active_typing_chats(self) -> Set[int]:
        """Get set of chat IDs with active typing indicators"""
        return {chat_id for chat_id, task in self._active_typing_tasks.items() 
                if not task.done()}
    
    async def cleanup(self) -> None:
        """Cleanup method to stop all typing indicators"""
        await self.stop_all_typing()
        self._typing_locks.clear()


class MessageQueueManager:
    """Manages message queuing to Redis lists per user to prevent parallel execution of send_ai_response."""
    
    def __init__(self, redis_url: str):
        """
        Initialize the MessageQueueManager.
        
        Args:
            redis_url: Redis connection URL
        """
        try:
            self.redis_client = redis.from_url(redis_url)
            # Test the connection
            self.redis_client.ping()
            logger.info("MessageQueueManager initialized with Redis URL: %s", redis_url)
        except Exception as e:
            logger.error("Failed to initialize MessageQueueManager with Redis URL %s: %s", redis_url, e)
            raise
    
    async def enqueue_message(self, user_id: int, chat_id: int, text: str, message_type: str = "regular", bot=None, typing_manager=None):
        """
        Enqueue a message for a user in their Redis list.
        
        Args:
            user_id: User ID
            chat_id: Chat ID
            text: Message text
            message_type: Type of message ("regular" or "proactive")
            bot: Telegram bot instance (for backward compatibility)
            typing_manager: TypingIndicatorManager instance (for backward compatibility)
        """
        try:
            # Validate inputs
            if not isinstance(user_id, int) or user_id <= 0:
                raise ValueError("user_id must be a positive integer")
            
            if not isinstance(chat_id, int) or chat_id <= 0:
                raise ValueError("chat_id must be a positive integer")
            
            if not text or not isinstance(text, str):
                raise ValueError("text must be a non-empty string")
            
            if message_type not in ["regular", "proactive"]:
                raise ValueError("message_type must be 'regular' or 'proactive'")
            
            # Create message payload
            message_data = {
                "user_id": user_id,
                "chat_id": chat_id,
                "text": text,
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": message_type,
                "retry_count": 0
            }
            
            # Serialize message data
            message_json = json.dumps(message_data, ensure_ascii=False)
            
            # Redis key for user's queue
            queue_key = f"queue:{user_id}"
            
            # Add message to user's Redis list using RPUSH
            result = self.redis_client.rpush(queue_key, message_json)
            
            # Add user to active users set
            self.redis_client.sadd("dispatcher:active_users", user_id)
            
            logger.info("Enqueued message for user %s (chat %s) of type %s. Queue position: %s",
                       user_id, chat_id, message_type, result)
            
            # For backward compatibility, if bot and typing_manager are provided, we can still call send_ai_response directly
            # This allows for a gradual migration
            if bot is not None and typing_manager is not None:
                # In a full implementation, we would remove this and only use the queue
                # But for now, we'll keep it for compatibility during transition
                pass
                
        except ValueError as e:
            logger.error("Validation error when enqueuing message for user %s: %s", user_id, e)
            raise
        except redis.RedisError as e:
            logger.error("Redis error when enqueuing message for user %s: %s", user_id, e)
            raise
        except Exception as e:
            logger.error("Unexpected error when enqueuing message for user %s: %s", user_id, e)
            raise
    
    async def get_queue_size(self, user_id: int) -> int:
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
                
            queue_key = f"queue:{user_id}"
            size = self.redis_client.llen(queue_key)
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
    
    async def is_queue_empty(self, user_id: int) -> bool:
        """
        Check if a user's queue is empty.
        
        Args:
            user_id: User ID
            
        Returns:
            True if queue is empty, False otherwise
        """
        try:
            size = await self.get_queue_size(user_id)
            return size == 0
        except Exception as e:
            logger.error("Error when checking if queue is empty for user %s: %s", user_id, e)
            raise


class MessageDispatcher:
    """Dispatches messages from Redis queues to send_ai_response function."""
    
    def __init__(self, redis_url: str, max_retries: int = 3, lock_timeout: int = 30):
        """
        Initialize the MessageDispatcher.
        
        Args:
            redis_url: Redis connection URL
            max_retries: Maximum number of retries for failed messages
            lock_timeout: Timeout for distributed locks in seconds
        """
        try:
            self.redis_client = redis.from_url(redis_url)
            # Test the connection
            self.redis_client.ping()
            logger.info("MessageDispatcher initialized with Redis URL: %s", redis_url)
            
            self.max_retries = max_retries
            self.lock_timeout = lock_timeout
            self.running = False
            
            # Initialize Telegram bot for sending messages
            self.bot = Bot(token=TELEGRAM_TOKEN)
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
            
        except Exception as e:
            logger.error("Failed to initialize MessageDispatcher with Redis URL %s: %s", redis_url, e)
            raise
    
    
    def acquire_lock(self, user_id: int) -> bool:
        """
        Acquire a distributed lock for a user queue.
        
        Args:
            user_id: User ID
            
        Returns:
            True if lock was acquired, False otherwise
        """
        try:
            lock_key = f"dispatcher:processing:{user_id}"
            result = self.lock_script(
                keys=[lock_key],
                args=[self.instance_id, self.lock_timeout]
            )
            lock_acquired = bool(result)
            
            if lock_acquired:
                logger.debug("Acquired lock for user %s (instance: %s)", user_id, self.instance_id)
            else:
                logger.debug("Failed to acquire lock for user %s (instance: %s)", user_id, self.instance_id)
                
            return lock_acquired
        except Exception as e:
            logger.error("Error acquiring lock for user %s: %s", user_id, e)
            return False
    
    def release_lock(self, user_id: int) -> bool:
        """
        Release a distributed lock for a user queue.
        
        Args:
            user_id: User ID
            
        Returns:
            True if lock was released, False otherwise
        """
        try:
            lock_key = f"dispatcher:processing:{user_id}"
            result = self.unlock_script(
                keys=[lock_key],
                args=[self.instance_id]
            )
            lock_released = bool(result)
            
            if lock_released:
                logger.debug("Released lock for user %s (instance: %s)", user_id, self.instance_id)
            else:
                logger.debug("Failed to release lock for user %s (instance: %s) - not owned by this instance", user_id, self.instance_id)
                
            return lock_released
        except Exception as e:
            logger.error("Error releasing lock for user %s: %s", user_id, e)
            return False
    
    def renew_lock(self, user_id: int) -> bool:
        """
        Renew a distributed lock for a user queue.
        
        Args:
            user_id: User ID
            
        Returns:
            True if lock was renewed, False otherwise
        """
        try:
            lock_key = f"dispatcher:processing:{user_id}"
            result = self.renew_script(
                keys=[lock_key],
                args=[self.instance_id, self.lock_timeout]
            )
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
                cursor, keys = self.redis_client.scan(cursor=cursor, match=pattern)
                scanned_count += len(keys)
                
                # Add users with non-empty queues to the active users set
                for key in keys:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    if key_str.startswith("queue:"):
                        try:
                            user_id = int(key_str.split(":")[1])
                            queue_size = self.redis_client.llen(key_str)
                            if queue_size > 0:
                                self.redis_client.sadd("dispatcher:active_users", user_id)
                                logger.info("Found existing queue for user %s with %s messages", user_id, queue_size)
                                added_count += 1
                            else:
                                logger.debug("Found empty queue for user %s", user_id)
                        except (ValueError, IndexError) as e:
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
                    active_users = self.redis_client.smembers("dispatcher:active_users")
                    
                    if not active_users:
                        # No active users, sleep for a bit
                        await asyncio.sleep(MESSAGE_QUEUE_DISPATCHER_INTERVAL)
                        continue
                    
                    # Process each active user
                    for user_id_bytes in active_users:
                        if not self.running:
                            break
                            
                        try:
                            user_id = int(user_id_bytes.decode('utf-8'))
                        except (ValueError, AttributeError) as e:
                            logger.warning("Invalid user ID in active users set: %s", user_id_bytes)
                            continue
                        
                        # Try to acquire processing lock for this user
                        lock_acquired = self.acquire_lock(user_id)
                        
                        if not lock_acquired:
                            # Another dispatcher is already processing this user's queue
                            continue
                        
                        try:
                            # Process messages for this user
                            await self.process_user_queue(user_id)
                        except Exception as e:
                            logger.error("Error processing queue for user %s: %s", user_id, e)
                        finally:
                            # Release the lock
                            self.release_lock(user_id)
                    
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
    
    async def process_user_queue(self, user_id: int):
        """
        Process messages from a user's queue.
        
        Args:
            user_id: User ID
        """
        # Create a task for lock renewal
        lock_renewal_task = asyncio.create_task(self._renew_lock_periodically(user_id))
        
        try:
            queue_key = f"queue:{user_id}"
            logger.info("Starting to process queue for user %s", user_id)
            
            # Process all messages in the queue
            message_count = 0
            while self.running:
                try:
                    # BLPOP blocks until a message is available or times out
                    result = self.redis_client.blpop([queue_key], timeout=1)
                except redis.RedisError as e:
                    logger.error("Redis error while fetching message from queue for user %s: %s", user_id, e)
                    # Continue with the loop to retry
                    await asyncio.sleep(0.1)
                    continue
                
                if not result:
                    # No more messages in queue, remove user from active set
                    try:
                        self.redis_client.srem("dispatcher:active_users", user_id)
                        logger.info("Finished processing queue for user %s. Processed %s messages", user_id, message_count)
                    except redis.RedisError as e:
                        logger.error("Redis error while removing user %s from active set: %s", user_id, e)
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
            logger.error("Redis error processing queue for user %s: %s", user_id, e)
        except Exception as e:
            logger.error("Error processing queue for user %s: %s", user_id, e)
        finally:
            # Cancel the lock renewal task
            lock_renewal_task.cancel()
            try:
                await lock_renewal_task
            except asyncio.CancelledError:
                pass
    
    async def _renew_lock_periodically(self, user_id: int):
        """
        Periodically renew the lock for a user queue.
        
        Args:
            user_id: User ID
        """
        try:
            while True:
                await asyncio.sleep(MESSAGE_QUEUE_LOCK_REFRESH_INTERVAL)
                lock_renewed = self.renew_lock(user_id)
                if not lock_renewed:
                    logger.warning("Failed to renew lock for user %s", user_id)
                    # If we can't renew the lock, we should stop processing
                    break
        except asyncio.CancelledError:
            # Task was cancelled, which is expected when processing is done
            pass
        except Exception as e:
            logger.error("Error in lock renewal task for user %s: %s", user_id, e)
    
    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Process a single message.
        
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
                    logger.error("Missing required field '%s' in message: %s", field, message)
                    return False
            
            user_id = message["user_id"]
            chat_id = message["chat_id"]
            text = message["text"]
            message_type = message["message_type"]
            retry_count = message.get("retry_count", 0)
            
            # Validate field types
            if not isinstance(user_id, int) or user_id <= 0:
                logger.error("Invalid user_id in message: %s", user_id)
                return False
                
            if not isinstance(chat_id, int) or chat_id <= 0:
                logger.error("Invalid chat_id in message: %s", chat_id)
                return False
                
            if not isinstance(text, str) or not text:
                logger.error("Invalid text in message: %s", text)
                return False
                
            if message_type not in ["regular", "proactive"]:
                logger.error("Invalid message_type in message: %s", message_type)
                return False
            
            logger.info("Processing message for user %s (chat %s) of type %s, retry count: %s",
                       user_id, chat_id, message_type, retry_count)
            
            # Send the message
            try:
                await send_ai_response(chat_id=chat_id, text=text, bot=self.bot, typing_manager=self.typing_manager)
            except Exception as e:
                logger.error("Error sending message for user %s: %s", user_id, e)
                return False
            
            logger.info("Successfully processed message for user %s", user_id)
            return True
            
        except Exception as e:
            logger.error("Error processing message: %s", e)
            return False
    
    async def handle_failed_message(self, message: Dict[str, Any]):
        """
        Handle a failed message.
        
        Args:
            message: Message data dictionary
        """
        try:
            user_id = message["user_id"]
            retry_count = message.get("retry_count", 0)
            
            if retry_count < self.max_retries:
                # Increment retry count and requeue
                message["retry_count"] = retry_count + 1
                message_json = json.dumps(message, ensure_ascii=False)
                queue_key = f"queue:{user_id}"
                self.redis_client.rpush(queue_key, message_json)
                logger.info("Requeued failed message for user %s (retry %s)", user_id, retry_count + 1)
            else:
                # Move to dead letter queue
                dlq_key = f"dlq:{user_id}"
                message_json = json.dumps(message, ensure_ascii=False)
                self.redis_client.rpush(dlq_key, message_json)
                logger.error("Moved message to dead letter queue for user %s after %s retries", user_id, self.max_retries)
                
        except Exception as e:
            logger.error("Error handling failed message for user %s: %s", message.get("user_id", "unknown"), e)


async def send_ai_response(chat_id: int, text: str, bot, typing_manager: 'TypingIndicatorManager' = None):
    """
    Splits AI response into safe message chunks and sends them sequentially with intelligent delays.
    
    :param chat_id: Telegram chat ID
    :param text: Raw AI model response (string)
    :param bot: Telegram bot instance
    :param typing_manager: TypingIndicatorManager instance (optional)
    """
    # Clean the text before processing
    text = clean_ai_response(text)
    
    # Split by paragraphs
    parts = text.split("\n\n")
    
    # Chunk long parts
    safe_parts = []
    for part in parts:
        chunks = textwrap.wrap(part, width=4000, break_long_words=False, break_on_hyphens=False)
        safe_parts.extend(chunks)
    
    # Send each processed part as an individual sendMessage call to Telegram in sequence
    for i, part in enumerate(safe_parts):
        # Add delay between messages (but not before the first message)
        if i > 0:
            # Calculate delay based on message length and random variation
            message_length = len(part)
            
            # Select a random typing speed between min and max
            typing_speed = random.randint(MIN_TYPING_SPEED, MAX_TYPING_SPEED)
            
            # Calculate base delay
            base_delay = message_length / typing_speed
            
            # Add random offset
            random_offset = random.uniform(RANDOM_OFFSET_MIN, RANDOM_OFFSET_MAX)
            
            # Calculate total delay
            delay = base_delay + random_offset
            
            # Ensure delay doesn't exceed maximum
            delay = min(delay, MAX_DELAY)
            
            # Start typing indicator if manager is provided and wait for the delay concurrently
            if typing_manager and delay > 0.7:
                # Start typing indicator
                await typing_manager.start_typing(bot, chat_id)
                
                # Wait for the calculated delay
                await asyncio.sleep(delay)
                
                # Stop typing indicator
                await typing_manager.stop_typing(chat_id)
            else:
                # Wait for the calculated delay without typing indicator
                await asyncio.sleep(delay)
        
        await bot.send_message(chat_id=chat_id, text=part)


async def generate_ai_response(
    ai_handler,
    typing_manager,
    bot,
    chat_id: int,
    additional_prompt: str,
    conversation_history: list,
    conversation_id: str = None,
    role: str = "user",
    show_typing: bool = True
) -> str:
    """
    Generate AI response with typing indicator management.
    
    Args:
        ai_handler: AIHandler instance
        typing_manager: TypingIndicatorManager instance
        bot: Telegram bot instance
        chat_id: Chat ID
        additional_prompt: Prompt to send to AI
        conversation_history: Conversation history
        conversation_id: Conversation ID for PromptAssembler
        role: Role for the prompt ("user" or "system")
        show_typing: Whether to show typing indicators
    
    Returns:
        AI response text or None if failed
    """
    try:
        logger.info("Starting AI request with typing indicator for chat %s", chat_id)
        
        # Start typing indicator BEFORE making LLM request if enabled
        if show_typing:
            await typing_manager.start_typing(bot, chat_id)
        
        # Make the actual AI request with timeout from config
        from config import REQUEST_TIMEOUT
        logger.info("Generating AI response for chat %s", chat_id)
        try:
            ai_response = await asyncio.wait_for(
                ai_handler.generate_response(additional_prompt, conversation_history, conversation_id, role),
                timeout=REQUEST_TIMEOUT
            )
            logger.info("AI response received for chat %s (%d chars)", chat_id, len(ai_response))
            return ai_response
        except asyncio.TimeoutError:
            logger.warning("AI request timeout for chat %s", chat_id)
            return None
        except Exception as e:
            logger.error("AI request failed for chat %s: %s", chat_id, e)
            return None
        
    except asyncio.TimeoutError:
        logger.warning("AI request timeout for chat %s", chat_id)
        return None
        
    except Exception as e:
        logger.error("AI request failed for chat %s: %s", chat_id, e)
        return None