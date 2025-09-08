import asyncio
import logging
import random
import time
from config import MIN_TYPING_SPEED, MAX_TYPING_SPEED, MAX_DELAY, RANDOM_OFFSET_MIN, RANDOM_OFFSET_MAX
import textwrap
import re
from typing import Dict, Set
from telegram import Bot

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