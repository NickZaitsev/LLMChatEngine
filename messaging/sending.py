"""Outgoing message delivery and AI-response generation helpers."""

import asyncio
import logging
import random
import traceback
from typing import Optional
from collections.abc import Hashable

from messaging.formatting import _split_ai_response
from messaging.typing import TypingIndicatorManager
from settings import settings as app_settings

MIN_TYPING_SPEED = app_settings.typing.min_speed
MAX_TYPING_SPEED = app_settings.typing.max_speed
MAX_DELAY = app_settings.typing.max_delay
RANDOM_OFFSET_MIN = app_settings.typing.random_offset_min
RANDOM_OFFSET_MAX = app_settings.typing.random_offset_max

logger = logging.getLogger(__name__)


async def send_ai_response(chat_id: int, text: str, bot, typing_manager: 'TypingIndicatorManager' = None, is_first_message: bool = True, route_key: Hashable | None = None):
    """
    Send an AI response, splitting long or multi-paragraph text into safe Telegram messages.

    :param chat_id: Telegram chat ID
    :param text: Message text
    :param bot: Telegram bot instance
    :param typing_manager: TypingIndicatorManager instance (optional)
    :param is_first_message: Whether the first emitted message should skip the typing delay
    """
    message_parts = _split_ai_response(text)
    if not message_parts:
        logger.warning("No message parts to send to chat %s", chat_id)
        return

    for index, part_text in enumerate(message_parts):
        should_delay = not (is_first_message and index == 0)

        if should_delay:
            message_length = len(part_text)
            typing_speed = random.randint(MIN_TYPING_SPEED, MAX_TYPING_SPEED)
            base_delay = message_length / typing_speed
            random_offset = random.uniform(RANDOM_OFFSET_MIN, RANDOM_OFFSET_MAX)
            delay = min(base_delay + random_offset, MAX_DELAY)

            if typing_manager and delay > 0.7:
                await typing_manager.start_typing(bot, chat_id, route_key=route_key)
                await asyncio.sleep(delay)
                await typing_manager.stop_typing(chat_id, route_key=route_key)
            else:
                await asyncio.sleep(delay)

        try:
            logger.debug("Sending message to chat %s (%d characters)", chat_id, len(part_text))
            await bot.send_message(chat_id=chat_id, text=part_text)
            logger.info("Successfully sent message to chat %s", chat_id)
        except Exception as e:
            logger.error("Failed to send message to chat %s: %s", chat_id, e)
            logger.error(traceback.format_exc())
            raise


async def generate_ai_response(
    ai_handler,
    typing_manager,
    bot,
    chat_id: int,
    additional_prompt: str,
    conversation_history: list,
    conversation_id: str = None,
    role: str = "user",
    show_typing: bool = True,
    route_key: Hashable | None = None
) -> str | None:
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
    typing_started = False
    try:
        logger.info("Starting AI request with typing indicator for chat %s", chat_id)

        # Start typing indicator BEFORE making LLM request if enabled
        if show_typing and typing_manager:
            await typing_manager.start_typing(bot, chat_id, route_key=route_key)
            typing_started = True

        # Make the actual AI request. AIHandler owns provider timeout/retry policy;
        # this wrapper owns typing-indicator lifetime and failure isolation.
        logger.info("Generating AI response for chat %s", chat_id)
        try:
            ai_response = await ai_handler.generate_response(
                additional_prompt,
                conversation_history,
                conversation_id,
                role,
            )
            if ai_response is None:
                logger.warning("AI generation returned no response for chat %s", chat_id)
                return None
            logger.info("AI response received for chat %s (%d chars)", chat_id, len(ai_response))
            return ai_response
        except TimeoutError:
            logger.warning("AI request timeout for chat %s", chat_id)
            return None
        except Exception as e:
            logger.error("AI request failed for chat %s: %s", chat_id, e)
            return None

    except TimeoutError:
        logger.warning("AI request timeout for chat %s", chat_id)
        return None

    except Exception as e:
        logger.error("AI request failed for chat %s: %s", chat_id, e)
        return None
    finally:
        if typing_started:
            try:
                await typing_manager.stop_typing(chat_id, route_key=route_key)
            except Exception as e:
                logger.warning("Failed to stop typing indicator for chat %s: %s", chat_id, e)
