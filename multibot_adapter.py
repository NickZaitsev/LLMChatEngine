"""
Multi-Bot Adapter for wrapping AIGirlfriendBot with custom configurations.

This module provides a way to instantiate bots with custom configurations
without modifying the original bot.py file.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
import uuid

from telegram.ext import Application

from config import TELEGRAM_TOKEN, BOT_NAME, BOT_PERSONALITY

logger = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Configuration for a single bot instance."""
    id: uuid.UUID
    token: str  # Decrypted token
    name: str
    personality: str
    is_active: bool
    feature_flags: Dict[str, Any]
    llm_config: Dict[str, Any]


def create_bot_with_config(bot_config: Optional[BotConfig] = None):
    """
    Create an AIGirlfriendBot instance with custom configuration.
    
    This function patches the necessary config values before instantiation
    and restores them afterward to avoid side effects.
    
    Args:
        bot_config: Optional BotConfig for multi-bot mode.
                   If None, creates a standard single-bot instance.
    
    Returns:
        AIGirlfriendBot instance with the specified configuration
    """
    import config
    from bot import AIGirlfriendBot
    
    if bot_config is None:
        # Standard single-bot mode
        bot = AIGirlfriendBot()
        bot.bot_config = None
        bot.bot_id = None
        bot.bot_name = BOT_NAME
        bot.bot_token = TELEGRAM_TOKEN
        bot.feature_flags = {}
        return bot
    
    # Save original config values
    original_token = config.TELEGRAM_TOKEN
    original_name = config.BOT_NAME
    original_personality = config.BOT_PERSONALITY
    
    try:
        # Temporarily patch config values
        config.TELEGRAM_TOKEN = bot_config.token
        config.BOT_NAME = bot_config.name
        config.BOT_PERSONALITY = bot_config.personality
        
        # Create bot with patched config
        bot = AIGirlfriendBot()
        
        # Attach multi-bot configuration
        bot.bot_config = bot_config
        bot.bot_id = bot_config.id
        bot.bot_name = bot_config.name
        bot.bot_token = bot_config.token
        bot.feature_flags = bot_config.feature_flags
        
        # Update AI handler personality
        if hasattr(bot, 'ai_handler') and bot.ai_handler:
            bot.ai_handler.update_personality(bot_config.personality)
            bot.ai_handler.apply_llm_config(bot_config.llm_config)
        
        logger.info("Created multi-bot instance: %s (%s)", bot_config.name, bot_config.id)
        return bot
        
    finally:
        # Restore original config values
        config.TELEGRAM_TOKEN = original_token
        config.BOT_NAME = original_name
        config.BOT_PERSONALITY = original_personality


def build_application_for_bot(bot, token: str) -> Application:
    """
    Build a Telegram Application for a bot with the specified token.
    
    Args:
        bot: AIGirlfriendBot instance
        token: Bot token to use
        
    Returns:
        Configured Application instance
    """
    # Call the bot's internal method if it exists
    if hasattr(bot, 'build_application'):
        return bot.build_application(token_override=token)
    
    # Otherwise build manually
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
    from config import POLLING_INTERVAL
    
    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.ALL, bot._monitor_pending_clear), group=-1)
    
    # Register handlers
    app.add_handler(CommandHandler("start", bot.start_command))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("clear", bot.clear_command))
    app.add_handler(CommandHandler("ok", bot.ok_command))
    app.add_handler(CommandHandler("stats", bot.stats_command))
    app.add_handler(CommandHandler("debug", bot.debug_command))
    app.add_handler(CommandHandler("status", bot.status_command))
    app.add_handler(CommandHandler("personality", bot.personality_command))
    app.add_handler(CommandHandler("stop", bot.stop_command))
    app.add_handler(CommandHandler("reset", bot.reset_command))
    app.add_handler(CommandHandler("ping", bot.ping_command))
    app.add_handler(CommandHandler("deps", bot.deps_command))
    
    # Callback query handler
    app.add_handler(CallbackQueryHandler(bot.handle_callback_query))
    
    # Message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, bot.handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, bot.handle_voice))
    
    # Error handler
    app.add_error_handler(bot.error_handler)
    
    return app
