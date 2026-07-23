"""Compatibility application context backed by the shared service container."""

from __future__ import annotations

import logging
import uuid
from typing import Optional, Tuple

from ai_handler import AIHandler
from prompt.assembler import PromptAssembler
from service_container import ServiceContainer

logger = logging.getLogger(__name__)


class AppContext:
    """Singleton facade for Celery and background jobs."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppContext, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self.container = ServiceContainer()
        self.conversation_manager = None
        self.memory_manager = None
        self.book_knowledge_manager = None
        self.prompt_assembler: PromptAssembler | None = None
        self.ai_handler: AIHandler | None = None
        self.message_queue_manager = None
        self.typing_manager = None
        self._initialized = True

    async def initialize(self) -> AppContext:
        """Initialize shared services through the composition root."""
        await self.container.initialize()
        self.conversation_manager = self.container.conversation_manager
        self.memory_manager = self.container.memory_manager
        self.book_knowledge_manager = self.container.book_knowledge_manager
        self.message_queue_manager = self.container.message_queue_manager
        self.typing_manager = self.container.typing_manager
        self.ai_handler = self.container.build_ai_handler()
        self.prompt_assembler = self.ai_handler.prompt_assembler
        logger.info("AppContext initialized from ServiceContainer.")
        return self

    async def get_ai_runtime_for_bot(
        self,
        bot_id: uuid.UUID | None = None,
    ) -> tuple[AIHandler, PromptAssembler | None]:
        """Build a bot-scoped AI runtime for background tasks."""
        await self.initialize()

        if not bot_id:
            ai_handler = self.container.build_ai_handler()
            return ai_handler, ai_handler.prompt_assembler

        bot_record = await self.container.storage.bots.get_bot(str(bot_id))
        if not bot_record:
            logger.warning("Bot config not found for task runtime: %s", bot_id)
            ai_handler = self.container.build_ai_handler()
            return ai_handler, ai_handler.prompt_assembler

        from core.bot_config import BotConfig

        bot_config = BotConfig(
            id=bot_record.id,
            token="",
            name=bot_record.name,
            personality=bot_record.personality,
            is_active=bot_record.is_active,
            feature_flags=bot_record.feature_flags or {},
            llm_config=bot_record.llm_config or {},
        )
        ai_handler = self.container.build_ai_handler(bot_config)
        return ai_handler, ai_handler.prompt_assembler


app_context = AppContext()


async def get_app_context() -> AppContext:
    """Return the initialized application context."""
    if not app_context.container._initialized:
        await app_context.initialize()
    return app_context
