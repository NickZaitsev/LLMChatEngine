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
from memory.llamaindex.embedding import LMStudioEmbeddingModel
from memory.llamaindex.gemini import GeminiEmbeddingModel
from llama_index.llms.lmstudio import LMStudio
from ai_handler import AIHandler
from config import (
    DATABASE_URL, USE_PGVECTOR, PROMPT_MAX_MEMORY_ITEMS, PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
    PROMPT_TRUNCATION_LENGTH, PROMPT_INCLUDE_SYSTEM_TEMPLATE, MESSAGE_QUEUE_REDIS_URL,
    TELEGRAM_TOKEN, MEMORY_ENABLED,
    VECTOR_STORE_TABLE_NAME, MEMORY_EMBED_MODEL, MEMORY_EMBED_DIM,
    MEMORY_EMBEDDING_PROVIDER, LMSTUDIO_BASE_URL, GEMINI_EMBEDDING_MODEL,
    MEMORY_RETRIEVAL_EXPAND_NEIGHBORS
)
from memory.manager import LlamaIndexMemoryManager
from memory.llamaindex.vector_store import PgVectorStore
from message_manager import MessageQueueManager, TypingIndicatorManager
from llama_index.llms.lmstudio import LMStudio
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
        self.memory_manager: Optional[LlamaIndexMemoryManager] = None
        self.prompt_assembler: Optional[PromptAssembler] = None
        self.ai_handler: Optional[AIHandler] = None
        self.message_queue_manager: Optional[MessageQueueManager] = None
        self.typing_manager: Optional[TypingIndicatorManager] = None
        self.bot: Optional[Bot] = None
        self._loop = None  # Track which event loop owns the current connections
        
        self._initialized = True
        logger.info("AppContext created but not yet initialized.")

    def _dispose_old_resources(self):
        """
        Best-effort cleanup of old database resources.
        
        When the event loop changes (e.g. between asyncio.run() calls in
        Celery tasks), we can't await async dispose because the old engine
        is bound to a now-closed loop. Instead, synchronously close the
        underlying connection pool and drop all references.
        """
        if self.conversation_manager and self.conversation_manager.storage:
            engine = self.conversation_manager.storage.engine
            if engine:
                try:
                    # The sync_engine's pool can be disposed synchronously
                    engine.sync_engine.pool.dispose()
                    logger.info("Disposed old Storage engine pool (sync).")
                except Exception as e:
                    logger.warning("Could not dispose old engine pool: %s (will be GC'd)", e)

    async def initialize(self):
        """
        Initializes all shared services. This should be called once on application startup.
        
        In Celery workers (prefork), each task may call asyncio.run() which creates
        a fresh event loop and closes it afterward. The async engine/sessions from a
        previous loop become invalid, so we detect loop changes and re-create all
        loop-bound components.
        """
        current_loop = asyncio.get_running_loop()
        
        # Check if we need to re-initialize due to loop change
        if self._loop is not None and self._loop is not current_loop:
            logger.warning(
                "Event loop changed (id %s -> %s). Re-initializing AppContext components.",
                id(self._loop), id(current_loop),
            )
            # Dispose old DB connections first to avoid leaked resources
            self._dispose_old_resources()
            # Reset all loop-bound components
            self.conversation_manager = None
            self.memory_manager = None
            self.prompt_assembler = None
            self.ai_handler = None
            self.message_queue_manager = None
            self.typing_manager = None
            self.bot = None
        
        if self.conversation_manager:
            logger.info("AppContext already initialized on current loop.")
            return

        self._loop = current_loop
        logger.info("Initializing AppContext on loop id=%s ...", id(current_loop))

        # 1. Initialize Conversation Manager (Database)
        try:
            self.conversation_manager = PostgresConversationManager(DATABASE_URL, USE_PGVECTOR)
            await self.conversation_manager.initialize()
            logger.info("PostgresConversationManager initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgresConversationManager: {e}")
            raise

        # 2. Initialize AI Handler (partially, to break dependency cycle)
        try:
            self.ai_handler = AIHandler()
            logger.info("AIHandler initialized (pre-prompt assembler).")
        except Exception as e:
            logger.error(f"Failed to initialize AIHandler: {e}")
            raise

        # 3. Initialize Memory Manager (LlamaIndex stack)
        try:
            if MEMORY_ENABLED:
                if MEMORY_EMBEDDING_PROVIDER == 'gemini':
                    embedding_model = GeminiEmbeddingModel(
                        model_name=GEMINI_EMBEDDING_MODEL
                    )
                    logger.info(f"Using Gemini embedding model: {GEMINI_EMBEDDING_MODEL}")
                elif MEMORY_EMBEDDING_PROVIDER == 'lmstudio':
                    embedding_model = LMStudioEmbeddingModel(
                        model_name=MEMORY_EMBED_MODEL
                    )
                    logger.info(f"Using lmstudio embedding model: {MEMORY_EMBED_MODEL}")
                else:
                    raise ValueError(f"Unsupported embedding provider: {MEMORY_EMBEDDING_PROVIDER}")

                logger.info(f"Using embedding dimension: {MEMORY_EMBED_DIM}")

                vector_store = PgVectorStore(
                    db_url=DATABASE_URL,
                    table_name=VECTOR_STORE_TABLE_NAME,
                    embed_dim=MEMORY_EMBED_DIM
                )

                self.memory_manager = LlamaIndexMemoryManager(
                    vector_store=vector_store,
                    embedding_model=embedding_model,
                    expand_neighbors=MEMORY_RETRIEVAL_EXPAND_NEIGHBORS,
                )
                logger.info("LlamaIndexMemoryManager initialized.")
            else:
                self.memory_manager = None
                logger.info("Memory is disabled. Skipping MemoryManager initialization.")

        except Exception as e:
            logger.error(f"Failed to initialize LlamaIndexMemoryManager: {e}")
            raise

        # 4. Initialize Prompt Assembler
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
                conversation_repo=self.conversation_manager.storage.conversations,
                user_repo=self.conversation_manager.storage.users,
                persona_repo=self.conversation_manager.storage.personas,
                config=prompt_config
            )
            logger.info("PromptAssembler initialized.")
        except Exception as e:
            logger.error(f"Failed to initialize PromptAssembler: {e}")
            raise
            
        # 5. Set Prompt Assembler in AI Handler
        if self.ai_handler and self.prompt_assembler:
            self.ai_handler.prompt_assembler = self.prompt_assembler
            logger.info("Prompt assembler set in AIHandler.")

        # 6. Initialize Message Queue Manager
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
    If not initialized or the loop has changed, it will initialize it first.
    """
    current_loop = asyncio.get_running_loop()
    if (not app_context._initialized
            or not app_context.conversation_manager
            or app_context._loop is not current_loop):
        await app_context.initialize()
    return app_context
