"""
Centralized Application Context for Shared Services

This module provides a singleton `AppContext` class that initializes and holds all
shared services, such as the database manager, AI handler, and memory manager.
This ensures that these components are created only once and can be reused
across the application, particularly in Celery tasks.
"""

import asyncio
import logging
from typing import Optional

from ai_handler import AIHandler
from config import (
    DATABASE_URL, USE_PGVECTOR, MEMORY_EMBED_MODEL, MEMORY_SUMMARIZER_MODE,
    MEMORY_CHUNK_OVERLAP, PROMPT_MAX_MEMORY_ITEMS, PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
    PROMPT_TRUNCATION_LENGTH, PROMPT_INCLUDE_SYSTEM_TEMPLATE, MESSAGE_QUEUE_REDIS_URL,
    TELEGRAM_TOKEN
)
from memory.manager import MemoryManager
from message_manager import MessageQueueManager, TypingIndicatorManager
from prompt.assembler import PromptAssembler
from storage_conversation_manager import PostgresConversationManager
from telegram import Bot

logger = logging.getLogger(__name__)

class AppContext:
    """Singleton class to hold all shared application services."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AppContext, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.conversation_manager: Optional[PostgresConversationManager] = None
        self.memory_manager: Optional[MemoryManager] = None
        self.prompt_assembler: Optional[PromptAssembler] = None
        self.ai_handler: Optional[AIHandler] = None
        self.message_queue_manager: Optional[MessageQueueManager] = None
        self.typing_manager: Optional[TypingIndicatorManager] = None
        self.bot: Optional[Bot] = None
        
        self._initialized = True
        logger.info("AppContext created but not yet initialized.")

    async def initialize(self):
        """
        Initializes all shared services. This should be called once on application startup.
        """
        if self.conversation_manager:
            logger.info("AppContext already initialized.")
            return

        logger.info("Initializing AppContext...")

        # 1. Initialize Conversation Manager (Database)
        try:
            self.conversation_manager = PostgresConversationManager(DATABASE_URL, USE_PGVECTOR)
            await self.conversation_manager.initialize()
            logger.info("PostgresConversationManager initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgresConversationManager: {e}")
            raise

        # 2. Initialize Memory Manager
        try:
            memory_config = {
                "embed_model": MEMORY_EMBED_MODEL,
                "summarizer_mode": MEMORY_SUMMARIZER_MODE,
                "chunk_overlap": MEMORY_CHUNK_OVERLAP
            }
            self.memory_manager = MemoryManager(
                message_repo=self.conversation_manager.storage.messages,
                memory_repo=self.conversation_manager.storage.memories,
                conversation_repo=self.conversation_manager.storage.conversations,
                config=memory_config
            )
            logger.info("MemoryManager initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryManager: {e}")
            raise

        # 3. Initialize Prompt Assembler
        try:
            prompt_config = {
                "max_memory_items": PROMPT_MAX_MEMORY_ITEMS,
                "memory_token_budget_ratio": PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
                "truncation_length": PROMPT_TRUNCATION_LENGTH,
                "include_system_template": PROMPT_INCLUDE_SYSTEM_TEMPLATE
            }
            self.prompt_assembler = PromptAssembler(
                message_repo=self.conversation_manager.storage.messages,
                memory_manager=self.memory_manager,
                persona_repo=self.conversation_manager.storage.personas,
                config=prompt_config
            )
            logger.info("PromptAssembler initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize PromptAssembler: {e}")
            raise

        # 4. Initialize AI Handler
        try:
            self.ai_handler = AIHandler(prompt_assembler=self.prompt_assembler)
            logger.info("AIHandler initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize AIHandler: {e}")
            raise

        # 5. Initialize Message Queue Manager
        try:
            self.message_queue_manager = MessageQueueManager(MESSAGE_QUEUE_REDIS_URL)
            logger.info("MessageQueueManager initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize MessageQueueManager: {e}")
            raise
            
        # 6. Initialize Typing Indicator Manager
        self.typing_manager = TypingIndicatorManager()
        logger.info("TypingIndicatorManager initialized.")

        # 7. Initialize Telegram Bot
        try:
            self.bot = Bot(token=TELEGRAM_TOKEN)
            logger.info("Telegram Bot initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize Telegram Bot: {e}")
            raise

        logger.info("AppContext initialization complete.")
        return self

# Global instance of the AppContext
app_context = AppContext()

async def get_app_context() -> AppContext:
    """
    Returns the initialized AppContext instance.
    If not initialized, it will initialize it first.
    """
    if not app_context._initialized or not app_context.conversation_manager:
        await app_context.initialize()
    return app_context