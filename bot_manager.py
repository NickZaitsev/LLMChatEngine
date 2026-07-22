"""
Bot Manager for running multiple bot instances.

This module provides the BotManager class which handles the lifecycle
of multiple user bot instances in a single process.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, Optional

from telegram.ext import Application

from core.bot_config import BotConfig
from features import BotFeature, has_feature
from service_container import ServiceContainer
from settings import build_settings
from token_encryption import decrypt_token

logger = logging.getLogger(__name__)


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
        self.bots: dict[uuid.UUID, Any] = {}  # bot_id -> AIGirlfriendBot instance
        self.applications: dict[uuid.UUID, Application] = {}  # bot_id -> Application
        self.bot_configs: dict[uuid.UUID, BotConfig] = {}  # bot_id -> BotConfig
        self.storage = None
        self.service_container = ServiceContainer(
            build_settings().model_copy(update={"DATABASE_URL": db_url})
        )
        self._running = False
        self._tasks: dict[uuid.UUID, asyncio.Task] = {}
        self._stop_events: dict[uuid.UUID, asyncio.Event] = {}
        self.shared_dispatcher = None
        self._shared_dispatcher_task: asyncio.Task | None = None
        self._dispatcher_watchdog_event = asyncio.Event()

    async def _init_storage(self):
        """Initialize database storage."""
        if self.storage is None:
            await self.service_container.initialize()
            self.storage = self.service_container.storage
            logger.info("Bot manager storage initialized")

    async def load_bots_from_db(self) -> None:
        """Load all active bots from database."""
        await self._init_storage()

        bots = await self.storage.bots.list_bots(is_active=True)

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

        if self._shared_dispatcher_task and self._shared_dispatcher_task.done():
            try:
                error = self._shared_dispatcher_task.exception()
            except asyncio.CancelledError:
                error = None
            if error is not None:
                logger.error("Shared message dispatcher task exited unexpectedly: %s", error)
            self._shared_dispatcher_task = None
            self.shared_dispatcher = None

        await self.service_container.initialize()
        self.shared_dispatcher = self.service_container.message_dispatcher
        self._shared_dispatcher_task = asyncio.create_task(self.shared_dispatcher.start_dispatching())
        self._shared_dispatcher_task.add_done_callback(self._on_dispatcher_done)
        logger.info("Shared message dispatcher started")

    def _on_dispatcher_done(self, task: asyncio.Future) -> None:
        """Wake the dispatcher watchdog immediately after an unexpected exit."""
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                logger.error("Shared message dispatcher crashed: %s", error)
        if self._running and self.bots:
            self._dispatcher_watchdog_event.set()

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
        from multibot_adapter import build_application_for_bot, create_bot_with_config

        bot_instance = create_bot_with_config(config, service_container=self.service_container)
        self.bots[bot_id] = bot_instance
        stop_event = asyncio.Event()
        self._stop_events[bot_id] = stop_event

        # Build and start application
        app = build_application_for_bot(bot_instance, config.token)
        self.applications[bot_id] = app

        # Start bot in background
        async def run_bot():
            """Initialize and poll one managed bot application."""
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

                await stop_event.wait()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Bot {bot_id} crashed: {e}")
            finally:
                self.bots.pop(bot_id, None)
                self._tasks.pop(bot_id, None)
                self._stop_events.pop(bot_id, None)
                if bot_id in self.applications:
                    await self._shutdown_application(app, bot_id)
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

        task = self._tasks.get(bot_id)
        stop_event = self._stop_events.get(bot_id)
        if stop_event:
            stop_event.set()
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._tasks.pop(bot_id, None)

        # Remove application
        self.applications.pop(bot_id, None)

        if not self.bots and self._shared_dispatcher_task:
            await self._stop_shared_dispatcher()

        logger.info(f"Stopped bot: {bot_name}")

    @staticmethod
    async def _shutdown_application(app: Application, bot_id: uuid.UUID) -> None:
        """Stop PTB application components independently."""
        for label, operation in (
            ("updater", app.updater.stop),
            ("application", app.stop),
            ("application resources", app.shutdown),
        ):
            try:
                await operation()
            except RuntimeError as exc:
                logger.debug("Bot %s %s was already stopped: %s", bot_id, label, exc)
            except Exception as exc:
                logger.error("Failed to stop bot %s %s: %s", bot_id, label, exc)

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

        dispatcher = self.service_container.message_dispatcher
        if dispatcher is not None:
            await dispatcher.invalidate_bot(str(bot_id))

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

            if hasattr(bot_instance, 'prompt_assembler') and bot_instance.prompt_assembler:
                bot_instance.prompt_assembler.personality = config.personality
                bot_instance.prompt_assembler.feature_flags = config.feature_flags or {}

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

        bot = await self.storage.bots.get_bot(str(bot_id))

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

        # Event-driven dispatcher watchdog.
        while self._running:
            await self._dispatcher_watchdog_event.wait()
            self._dispatcher_watchdog_event.clear()
            if not self._running:
                break
            if self.bots and (self._shared_dispatcher_task is None or self._shared_dispatcher_task.done()):
                try:
                    await self._ensure_shared_dispatcher()
                except Exception as e:
                    logger.error("Failed to ensure shared dispatcher while bots are running: %s", e)

    async def stop_all(self) -> None:
        """Stop all running bots."""
        self._running = False
        self._dispatcher_watchdog_event.set()

        # Stop all bots
        bot_ids = list(self.bots.keys())
        for bot_id in bot_ids:
            await self.stop_bot(bot_id)

        if self._shared_dispatcher_task:
            await self._stop_shared_dispatcher()

        logger.info("All bots stopped")
