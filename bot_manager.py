"""
Bot Manager for running multiple bot instances.

This module provides the BotManager class which handles the lifecycle
of multiple user bot instances in a single process.
"""

import asyncio
import logging
import uuid
from typing import Dict, Optional, Any
from dataclasses import dataclass

from telegram.ext import Application

from token_encryption import decrypt_token
from features import BotFeature, has_feature
from message_manager import MessageDispatcher
from config import MESSAGE_QUEUE_REDIS_URL, MESSAGE_QUEUE_MAX_RETRIES, MESSAGE_QUEUE_LOCK_TIMEOUT

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


class BotManager:
    """
    Manages multiple bot instances in a single process.
    
    This class handles:
    - Loading bot configurations from database
    - Starting/stopping individual bots
    - Hot-reloading bot configurations
    - Running all bots concurrently
    """
    
    def __init__(self, db_url: str):
        """
        Initialize the bot manager.
        
        Args:
            db_url: PostgreSQL database URL
        """
        self.db_url = db_url
        self.bots: Dict[uuid.UUID, Any] = {}  # bot_id -> AIGirlfriendBot instance
        self.applications: Dict[uuid.UUID, Application] = {}  # bot_id -> Application
        self.bot_configs: Dict[uuid.UUID, BotConfig] = {}  # bot_id -> BotConfig
        self.storage = None
        self._running = False
        self._tasks: Dict[uuid.UUID, asyncio.Task] = {}
        self.shared_dispatcher: Optional[MessageDispatcher] = None
        self._shared_dispatcher_task: Optional[asyncio.Task] = None
    
    async def _init_storage(self):
        """Initialize database storage."""
        if self.storage is None:
            from storage import create_storage
            self.storage = await create_storage(self.db_url)
            logger.info("Bot manager storage initialized")
    
    async def load_bots_from_db(self) -> None:
        """Load all active bots from database."""
        await self._init_storage()
        
        from storage.models import Bot
        from sqlalchemy import select
        
        async with self.storage.session_maker() as session:
            result = await session.execute(
                select(Bot).where(Bot.is_active == True)
            )
            bots = result.scalars().all()
        
        logger.info(f"Found {len(bots)} active bots in database")
        
        for bot in bots:
            try:
                decrypted_token = decrypt_token(bot.token_encrypted)
                config = BotConfig(
                    id=bot.id,
                    token=decrypted_token,
                    name=bot.name,
                    personality=bot.personality,
                    is_active=bot.is_active,
                    feature_flags=bot.feature_flags or {},
                    llm_config=bot.llm_config or {}
                )
                self.bot_configs[bot.id] = config
                logger.info(f"Loaded bot config: {bot.name} ({bot.id})")
            except Exception as e:
                logger.error(f"Failed to load bot {bot.id}: {e}")

    async def _ensure_shared_dispatcher(self) -> None:
        """Start a single shared dispatcher for all bot instances."""
        if self._shared_dispatcher_task and not self._shared_dispatcher_task.done():
            return

        self.shared_dispatcher = MessageDispatcher(
            MESSAGE_QUEUE_REDIS_URL,
            MESSAGE_QUEUE_MAX_RETRIES,
            MESSAGE_QUEUE_LOCK_TIMEOUT
        )
        self._shared_dispatcher_task = asyncio.create_task(self.shared_dispatcher.start_dispatching())
        logger.info("Shared message dispatcher started")

    async def _stop_shared_dispatcher(self) -> None:
        """Stop the shared dispatcher if it is running."""
        if self.shared_dispatcher:
            await self.shared_dispatcher.stop_dispatching()
        if self._shared_dispatcher_task:
            self._shared_dispatcher_task.cancel()
            try:
                await self._shared_dispatcher_task
            except asyncio.CancelledError:
                pass
            self._shared_dispatcher_task = None
        self.shared_dispatcher = None
        logger.info("Shared message dispatcher stopped")
    
    async def start_bot(self, bot_id: uuid.UUID) -> None:
        """
        Start a specific bot by ID.
        
        Args:
            bot_id: UUID of the bot to start
        """
        if bot_id in self.bots:
            logger.warning(f"Bot {bot_id} is already running")
            return
        
        # Load config if not already loaded
        if bot_id not in self.bot_configs:
            await self._load_single_bot_config(bot_id)
        
        config = self.bot_configs.get(bot_id)
        if not config:
            raise ValueError(f"Bot config not found: {bot_id}")
        
        if not config.is_active:
            raise ValueError(f"Bot {bot_id} is not active")
        
        # Create bot instance using adapter
        from multibot_adapter import create_bot_with_config, build_application_for_bot, BotConfig
        
        bot_instance = create_bot_with_config(config)
        self.bots[bot_id] = bot_instance
        
        # Build and start application
        app = build_application_for_bot(bot_instance, config.token)
        self.applications[bot_id] = app
        
        # Start bot in background
        async def run_bot():
            try:
                await self._ensure_shared_dispatcher()

                # Initialize bot storage and components
                if hasattr(bot_instance, '_initialize_storage'):
                    await bot_instance._initialize_storage()
                
                if hasattr(bot_instance, '_initialize_memory_components'):
                    await bot_instance._initialize_memory_components()
                
                if hasattr(bot_instance, '_initialize_lmstudio_model'):
                    await bot_instance._initialize_lmstudio_model()
                
                await app.initialize()
                await app.start()
                await app.updater.start_polling()
                logger.info(f"Bot {config.name} ({bot_id}) started successfully")
                
                # Wait until stopped
                while bot_id in self.bots:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Bot {bot_id} crashed: {e}")
            finally:
                self.bots.pop(bot_id, None)
                self._tasks.pop(bot_id, None)
                if bot_id in self.applications:
                    try:
                        await app.updater.stop()
                        await app.stop()
                        await app.shutdown()
                    except Exception:
                        pass
                    self.applications.pop(bot_id, None)
                if not self.bots and self._shared_dispatcher_task:
                    await self._stop_shared_dispatcher()
        
        self._tasks[bot_id] = asyncio.create_task(run_bot())
        logger.info(f"Started bot: {config.name}")
    
    async def stop_bot(self, bot_id: uuid.UUID) -> None:
        """
        Stop a specific bot by ID.
        
        Args:
            bot_id: UUID of the bot to stop
        """
        if bot_id not in self.bots:
            logger.warning(f"Bot {bot_id} is not running")
            return
        
        bot_name = self.bot_configs[bot_id].name if bot_id in self.bot_configs else str(bot_id)
        
        # Remove from bots dict (triggers shutdown in run loop)
        del self.bots[bot_id]
        
        # Cancel task
        if bot_id in self._tasks:
            self._tasks[bot_id].cancel()
            try:
                await self._tasks[bot_id]
            except asyncio.CancelledError:
                pass
            self._tasks.pop(bot_id, None)
        
        # Remove application
        self.applications.pop(bot_id, None)

        if not self.bots and self._shared_dispatcher_task:
            await self._stop_shared_dispatcher()
        
        logger.info(f"Stopped bot: {bot_name}")
    
    async def reload_bot_config(self, bot_id: uuid.UUID) -> None:
        """
        Hot-reload bot personality/config without full restart.
        
        Args:
            bot_id: UUID of the bot to reload
        """
        old_config = self.bot_configs.get(bot_id)

        # Reload config from database
        await self._load_single_bot_config(bot_id)
        config = self.bot_configs.get(bot_id)
        
        if not config:
            raise ValueError(f"Bot config not found: {bot_id}")
        
        # If bot is running, update its config
        if bot_id in self.bots:
            bot_instance = self.bots[bot_id]

            if not config.is_active:
                await self.stop_bot(bot_id)
                logger.info(f"Stopped inactive bot after reload: {config.name}")
                return

            requires_restart = (
                old_config is not None and old_config.token != config.token
            )

            bot_instance.bot_config = config
            bot_instance.bot_name = config.name
            bot_instance.bot_token = config.token
            bot_instance.feature_flags = config.feature_flags

            if hasattr(bot_instance, 'ai_handler') and bot_instance.ai_handler:
                bot_instance.ai_handler.update_personality(config.personality)
                bot_instance.ai_handler.apply_llm_config(config.llm_config)

            if requires_restart:
                logger.info(f"Bot token changed for {config.name}; restarting bot")
                await self.stop_bot(bot_id)
                await self.start_bot(bot_id)
                return

            logger.info(f"Hot-reloaded config for bot: {config.name}")
        else:
            # Bot not running, check if it should be started
            if config.is_active:
                await self.start_bot(bot_id)
    
    async def _load_single_bot_config(self, bot_id: uuid.UUID) -> None:
        """Load a single bot's config from database."""
        await self._init_storage()
        
        from storage.models import Bot
        from sqlalchemy import select
        
        async with self.storage.session_maker() as session:
            result = await session.execute(
                select(Bot).where(Bot.id == bot_id)
            )
            bot = result.scalar_one_or_none()
        
        if not bot:
            logger.warning(f"Bot not found in database: {bot_id}")
            return
        
        try:
            decrypted_token = decrypt_token(bot.token_encrypted)
            config = BotConfig(
                id=bot.id,
                token=decrypted_token,
                name=bot.name,
                personality=bot.personality,
                is_active=bot.is_active,
                feature_flags=bot.feature_flags or {},
                llm_config=bot.llm_config or {}
            )
            self.bot_configs[bot.id] = config
        except Exception as e:
            logger.error(f"Failed to load bot config {bot_id}: {e}")
    
    async def run_all(self) -> None:
        """Run all loaded bots using asyncio."""
        self._running = True
        
        # Start all configured bots
        for bot_id, config in self.bot_configs.items():
            if config.is_active:
                try:
                    await self.start_bot(bot_id)
                except Exception as e:
                    logger.error(f"Failed to start bot {config.name}: {e}")
        
        logger.info(f"Running {len(self.bots)} bots")
        
        # Keep running until stopped
        while self._running:
            await asyncio.sleep(1)
    
    async def stop_all(self) -> None:
        """Stop all running bots."""
        self._running = False
        
        # Stop all bots
        bot_ids = list(self.bots.keys())
        for bot_id in bot_ids:
            await self.stop_bot(bot_id)

        if self._shared_dispatcher_task:
            await self._stop_shared_dispatcher()
        
        logger.info("All bots stopped")
