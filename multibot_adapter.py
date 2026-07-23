"""
Multi-bot adapter for wrapping TelegramChatBot with custom configurations.

This module provides a way to instantiate bots with custom configurations.
"""

import logging
from typing import Optional

from telegram.ext import Application

from core.bot_config import BotConfig
from service_container import ServiceContainer

logger = logging.getLogger(__name__)


def create_bot_with_config(
    bot_config: BotConfig | None = None,
    service_container: ServiceContainer | None = None,
):
    """
    Create a TelegramChatBot instance with custom configuration.

    Args:
        bot_config: Optional BotConfig for multi-bot mode.
                   If None, creates a standard single-bot instance.

    Returns:
        TelegramChatBot instance with the specified configuration
    """
    from bot import TelegramChatBot

    bot = TelegramChatBot(bot_config=bot_config, service_container=service_container)
    if bot_config is not None:
        logger.info("Created multi-bot instance: %s (%s)", bot_config.name, bot_config.id)
    return bot


def build_application_for_bot(bot, token: str) -> Application:
    """
    Build a Telegram Application for a bot with the specified token.

    Args:
        bot: TelegramChatBot instance
        token: Bot token to use

    Returns:
        Configured Application instance
    """
    return bot.build_application(token_override=token)
