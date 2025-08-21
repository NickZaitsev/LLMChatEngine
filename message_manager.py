import asyncio
import logging
import textwrap
from typing import Dict, Set
from telegram import Bot

logger = logging.getLogger(__name__)


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


async def send_ai_response(chat_id: int, text: str, bot):
    """
    Splits AI response into safe message chunks and sends them sequentially.
    
    :param chat_id: Telegram chat ID
    :param text: Raw AI model response (string)
    :param bot: Telegram bot instance
    """
    # Split by paragraphs
    parts = text.split("\n\n")
    
    # Chunk long parts
    safe_parts = []
    for part in parts:
        chunks = textwrap.wrap(part, width=4000, break_long_words=False, break_on_hyphens=False)
        safe_parts.extend(chunks)
    
    # Send each processed part as an individual sendMessage call to Telegram in sequence
    for part in safe_parts:
        await bot.send_message(chat_id=chat_id, text=part)