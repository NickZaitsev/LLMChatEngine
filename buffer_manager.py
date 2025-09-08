import asyncio
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable, Any
from config import (
    BUFFER_SHORT_MESSAGE_TIMEOUT,
    BUFFER_LONG_MESSAGE_TIMEOUT,
    BUFFER_MAX_MESSAGES,
    BUFFER_WORD_COUNT_THRESHOLD,
    BUFFER_CLEANUP_INTERVAL
)
import logging

logger = logging.getLogger(__name__)


@dataclass
class MessageBufferEntry:
    """Data class to store individual messages with timestamps"""
    user_id: int
    message: str
    timestamp: float
    word_count: int


class UserBuffer:
    """Manages per-user message buffers"""
    
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.messages: List[MessageBufferEntry] = []
        self.last_activity = time.time()
        self._lock = asyncio.Lock()
    
    async def add_message(self, message: str) -> None:
        """Add a message to the user's buffer"""
        async with self._lock:
            word_count = len(message.split())
            entry = MessageBufferEntry(
                user_id=self.user_id,
                message=message,
                timestamp=time.time(),
                word_count=word_count
            )
            
            self.messages.append(entry)
            self.last_activity = time.time()
            logger.debug(f"Added message to buffer for user {self.user_id}. Buffer size: {len(self.messages)}")
    
    async def get_buffer_size(self) -> int:
        """Get the current buffer size"""
        async with self._lock:
            return len(self.messages)
    
    async def is_empty(self) -> bool:
        """Check if the buffer is empty"""
        async with self._lock:
            return len(self.messages) == 0
    
    async def clear(self) -> None:
        """Clear all messages from the buffer"""
        async with self._lock:
            self.messages.clear()
            self.last_activity = time.time()
            logger.debug(f"Cleared buffer for user {self.user_id}")
    
    async def get_messages(self) -> List[MessageBufferEntry]:
        """Get all messages in the buffer"""
        async with self._lock:
            return self.messages.copy()
    
    async def get_concatenated_message(self) -> str:
        """Concatenate all messages in the buffer"""
        async with self._lock:
            if not self.messages:
                return ""
            
            # Join messages with a newline, preserving order
            concatenated = "\n".join(entry.message for entry in self.messages)
            logger.debug(f"Concatenated {len(self.messages)} messages for user {self.user_id}")
            return concatenated
    
    async def should_dispatch_immediately(self) -> bool:
        """Check if messages should be dispatched immediately based on content or buffer size"""
        async with self._lock:
            # Dispatch immediately if we have too many messages
            if len(self.messages) >= BUFFER_MAX_MESSAGES:
                logger.debug(f"Buffer full for user {self.user_id}, should dispatch immediately")
                return True
            
            # Dispatch immediately if any message is long
            for entry in self.messages:
                if entry.word_count >= BUFFER_WORD_COUNT_THRESHOLD:
                    logger.debug(f"Long message detected for user {self.user_id}, should dispatch immediately")
                    return True
            
            return False


class BufferManager:
    """Coordinates all user buffers and manages dispatch logic"""
    
    def __init__(self):
        self.user_buffers: Dict[int, UserBuffer] = {}
        self._lock = asyncio.Lock()
        self.dispatch_callbacks: Dict[int, asyncio.Task] = {}
        self.typing_indicators: Dict[int, asyncio.Task] = {}  # Track typing indicator tasks
        self.typing_manager = None # Will be set by the bot
        self.bot_instances: Dict[int, Any] = {}  # Map user_id to bot instance
        self.chat_ids: Dict[int, int] = {}  # Map user_id to chat_id
    
    def set_typing_manager(self, typing_manager) -> None:
        """Set the typing manager instance"""
        self.typing_manager = typing_manager
    
    def set_user_context(self, user_id: int, bot, chat_id: int) -> None:
        """Set the bot instance and chat ID for a user"""
        self.bot_instances[user_id] = bot
        self.chat_ids[user_id] = chat_id
    
    async def _start_typing_indicator(self, user_id: int) -> None:
        """Start typing indicator for a user when messages are buffered"""
        # Cancel any existing typing indicator for this user
        await self._stop_typing_indicator(user_id)
        
        # Only start typing indicator if we have the required components
        if (self.typing_manager and
            user_id in self.bot_instances and
            user_id in self.chat_ids):
            
            bot = self.bot_instances[user_id]
            chat_id = self.chat_ids[user_id]
            
            # Create and start typing indicator task
            async def _typing_task():
                try:
                    await self.typing_manager.start_typing(bot, chat_id)
                    logger.debug(f"Started typing indicator for buffered messages from user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to start typing indicator for user {user_id}: {e}")
            
            task = asyncio.create_task(_typing_task())
            self.typing_indicators[user_id] = task
    
    async def _stop_typing_indicator(self, user_id: int) -> None:
        """Stop typing indicator for a user"""
        if user_id in self.typing_indicators:
            task = self.typing_indicators[user_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            del self.typing_indicators[user_id]
        
        # Stop the actual typing indicator if typing manager is available
        if self.typing_manager and user_id in self.chat_ids:
            chat_id = self.chat_ids[user_id]
            # Create task to stop typing indicator
            async def _stop_typing_task():
                try:
                    await self.typing_manager.stop_typing(chat_id)
                    logger.debug(f"Stopped typing indicator for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to stop typing indicator for user {user_id}: {e}")
            
            await _stop_typing_task()
    
    def get_user_buffer(self, user_id: int) -> UserBuffer:
        """Get or create a buffer for a user"""
        if user_id not in self.user_buffers:
            self.user_buffers[user_id] = UserBuffer(user_id)
            logger.debug(f"Created new buffer for user {user_id}")
        
        return self.user_buffers[user_id]
    
    async def add_message(self, user_id: int, message: str) -> None:
        """Add a message to a user's buffer"""
        buffer = self.get_user_buffer(user_id)
        await buffer.add_message(message)
        
        # Start typing indicator when first message is added to buffer
        buffer_size = await buffer.get_buffer_size()
        if buffer_size == 1:
            await self._start_typing_indicator(user_id)
    
    async def get_adaptive_timeout(self, user_id: int) -> float:
        """Calculate adaptive timeout based on message content and buffer size"""
        buffer = self.get_user_buffer(user_id)
        
        # If buffer is empty, return default timeout
        if await buffer.is_empty():
            return BUFFER_SHORT_MESSAGE_TIMEOUT
        
        # If buffer has long messages or many messages, use short timeout
        if await buffer.should_dispatch_immediately():
            return BUFFER_LONG_MESSAGE_TIMEOUT
        
        # Default to short message timeout
        return BUFFER_SHORT_MESSAGE_TIMEOUT
    
    async def schedule_dispatch(self, user_id: int, dispatch_func: Callable) -> None:
        """Schedule a dispatch callback based on adaptive timeout"""
        # Cancel any existing dispatch task for this user
        if user_id in self.dispatch_callbacks:
            task = self.dispatch_callbacks[user_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Calculate timeout
        timeout = await self.get_adaptive_timeout(user_id)
        logger.debug(f"Scheduling dispatch for user {user_id} in {timeout} seconds")
        
        # Stop typing indicator when scheduling a new dispatch
        await self._stop_typing_indicator(user_id)
        
        # Create and store new dispatch task
        async def _dispatch_with_timeout():
            try:
                await asyncio.sleep(timeout)
                # Check if dispatch_func is a coroutine function or a regular function
                if asyncio.iscoroutinefunction(dispatch_func):
                    await dispatch_func(user_id)
                else:
                    dispatch_func(user_id)
            except Exception as e:
                logger.error(f"Error in dispatch task for user {user_id}: {e}")
        
        task = asyncio.create_task(_dispatch_with_timeout())
        self.dispatch_callbacks[user_id] = task
    
    async def dispatch_buffer(self, user_id: int) -> Optional[str]:
        """Dispatch the buffer for a user and return concatenated message"""
        async with self._lock:
            if user_id not in self.user_buffers:
                logger.debug(f"No buffer found for user {user_id}")
                return None
            
            buffer = self.user_buffers[user_id]
            
            if await buffer.is_empty():
                logger.debug(f"Buffer is empty for user {user_id}")
                return None
            
            # Get concatenated message
            concatenated_message = await buffer.get_concatenated_message()
            
            # Clear the buffer
            await buffer.clear()
            
            # Stop typing indicator when messages are dispatched
            await self._stop_typing_indicator(user_id)
            
            logger.info(f"Dispatched buffer for user {user_id} with {len(concatenated_message.split())} words")
            return concatenated_message
    
    async def get_buffer_size(self, user_id: int) -> int:
        """Get the current buffer size for a user"""
        if user_id in self.user_buffers:
            return await self.user_buffers[user_id].get_buffer_size()
        return 0
    
    async def cleanup_inactive_buffers(self, max_age_seconds: int = BUFFER_CLEANUP_INTERVAL) -> None:
        """Remove buffers that haven't been active for a specified time"""
        current_time = time.time()
        inactive_users = []
        
        async with self._lock:
            for user_id, buffer in self.user_buffers.items():
                if current_time - buffer.last_activity > max_age_seconds:
                    inactive_users.append(user_id)
            
            for user_id in inactive_users:
                if user_id in self.user_buffers:
                    del self.user_buffers[user_id]
                    logger.debug(f"Removed inactive buffer for user {user_id}")
                
                # Cancel any pending dispatch tasks
                if user_id in self.dispatch_callbacks:
                    task = self.dispatch_callbacks[user_id]
                    if not task.done():
                        task.cancel()
                    del self.dispatch_callbacks[user_id]
                
                # Stop typing indicator for inactive user
                await self._stop_typing_indicator(user_id)