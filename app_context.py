"""
Centralized Application Context for Shared Services

This module provides a singleton `AppContext` class that initializes and holds all
shared services, such as the database manager, AI handler, and memory manager.
This ensures that these components are created only once and can be reused
across the application, particularly in Celery tasks.
"""

import logging
import uuid
from typing import Optional, Tuple
from ai_handler import AIHandler
from config import (
    DATABASE_URL, USE_PGVECTOR, PROMPT_MAX_MEMORY_ITEMS, PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
    PROMPT_TRUNCATION_LENGTH, PROMPT_INCLUDE_SYSTEM_TEMPLATE, MESSAGE_QUEUE_REDIS_URL,
    TELEGRAM_TOKEN, MEMORY_ENABLED,
    VECTOR_STORE_TABLE_NAME, MEMORY_EMBED_MODEL, MEMORY_EMBED_DIM,
    MEMORY_EMBEDDING_PROVIDER, LMSTUDIO_BASE_URL, GEMINI_EMBEDDING_MODEL,
    MEMORY_RETRIEVAL_EXPAND_NEIGHBORS, BOOK_RAG_ENABLED, BOOK_RAG_EXPAND_NEIGHBORS
)
from knowledge.manager import BookKnowledgeManager
from knowledge.store import BookVectorStore
from memory.manager import LlamaIndexMemoryManager
from memory.llamaindex.vector_store import PgVectorStore
from memory.embedding_factory import build_embedding_model
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
        self.memory_manager: Optional[LlamaIndexMemoryManager] = None
        self.book_knowledge_manager: Optional[BookKnowledgeManager] = None
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

        logger.info("Initializing AppContext ...")

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
            embedding_model = build_embedding_model() if (MEMORY_ENABLED or BOOK_RAG_ENABLED) else None

            if MEMORY_ENABLED:
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

            if BOOK_RAG_ENABLED and embedding_model:
                book_store = BookVectorStore(
                    db_url=DATABASE_URL,
                    table_name="book_chunks",
                    embed_dim=MEMORY_EMBED_DIM,
                )
                self.book_knowledge_manager = BookKnowledgeManager(
                    store=book_store,
                    embedding_model=embedding_model,
                    expand_neighbors=BOOK_RAG_EXPAND_NEIGHBORS,
                )
                logger.info("BookKnowledgeManager initialized.")
            else:
                self.book_knowledge_manager = None
                logger.info("Book RAG is disabled. Skipping BookKnowledgeManager initialization.")

        except Exception as e:
            logger.error(f"Failed to initialize vector managers: {e}")
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
                user_settings_repo=self.conversation_manager.storage.user_settings,
                book_knowledge_manager=self.book_knowledge_manager,
                config=prompt_config
            )
            self.prompt_assembler.personality = self.ai_handler.personality
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

    async def get_ai_runtime_for_bot(self, bot_id: Optional[uuid.UUID] = None) -> Tuple[AIHandler, Optional[PromptAssembler]]:
        """
        Build a bot-scoped AI runtime for background tasks.

        The live bot process already has per-bot AIHandler/PromptAssembler instances.
        Celery tasks run through AppContext, so they need an explicit per-bot clone
        to avoid falling back to the default provider/model/personality.
        """
        await self.initialize()

        prompt_assembler = None
        if self.conversation_manager and self.conversation_manager.storage:
            prompt_config = {
                "max_memory_items": PROMPT_MAX_MEMORY_ITEMS,
                "memory_token_budget_ratio": PROMPT_MEMORY_TOKEN_BUDGET_RATIO,
                "truncation_length": PROMPT_TRUNCATION_LENGTH,
                "include_system_template": PROMPT_INCLUDE_SYSTEM_TEMPLATE
            }
            prompt_assembler = PromptAssembler(
                message_repo=self.conversation_manager.storage.messages,
                memory_manager=self.memory_manager,
                conversation_repo=self.conversation_manager.storage.conversations,
                user_repo=self.conversation_manager.storage.users,
                user_settings_repo=self.conversation_manager.storage.user_settings,
                book_knowledge_manager=self.book_knowledge_manager,
                config=prompt_config
            )
            prompt_assembler.personality = self.ai_handler.personality

        ai_handler = AIHandler(prompt_assembler=prompt_assembler)

        if not bot_id:
            return ai_handler, prompt_assembler

        try:
            bot_record = await self.conversation_manager.storage.bots.get_bot(str(bot_id))

            if bot_record:
                ai_handler.update_personality(bot_record.personality)
                ai_handler.apply_llm_config(bot_record.llm_config or {})
                if prompt_assembler:
                    prompt_assembler.personality = bot_record.personality
                    prompt_assembler.feature_flags = bot_record.feature_flags or {}
            else:
                logger.warning("Bot config not found for task runtime: %s", bot_id)
        except Exception as e:
            logger.error("Failed to build bot-scoped AI runtime for %s: %s", bot_id, e)

        return ai_handler, prompt_assembler

# Global instance of the AppContext
app_context = AppContext()

async def get_app_context() -> AppContext:
    """
    Returns the initialized AppContext instance.
    If not initialized or the loop has changed, it will initialize it first.
    """
    if (not app_context._initialized
            or not app_context.conversation_manager):
        await app_context.initialize()
    return app_context
