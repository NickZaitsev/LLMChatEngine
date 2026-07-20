"""Process-level service composition for runtime components."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from ai_handler import AIHandler
from core.abstractions import EmbeddingModel
from core.bot_config import BotConfig
from memory.embedding_factory import build_embedding_model
from messaging.token_resolver import BotTokenResolver
from messaging import MessageDispatcher, MessageQueueManager, TypingIndicatorManager
from prompt.assembler import PromptAssembler
from settings import AppSettings, build_settings
from storage import Storage, create_storage
from storage_conversation_manager import PostgresConversationManager

if TYPE_CHECKING:
    from knowledge.manager import BookKnowledgeManager
    from knowledge.store import BookVectorStore
    from memory.llamaindex.vector_store import PgVectorStore
    from memory.manager import LlamaIndexMemoryManager

logger = logging.getLogger(__name__)


class ServiceContainer:
    """Own shared services that should be constructed once per process."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or build_settings()
        self.storage: Optional[Storage] = None
        self.conversation_manager: Optional[PostgresConversationManager] = None
        self.embedding_model: Optional[EmbeddingModel] = None
        self.memory_vector_store: Optional["PgVectorStore"] = None
        self.memory_manager: Optional["LlamaIndexMemoryManager"] = None
        self.book_vector_store: Optional["BookVectorStore"] = None
        self.book_knowledge_manager: Optional["BookKnowledgeManager"] = None
        self.message_queue_manager: Optional[MessageQueueManager] = None
        self.typing_manager: Optional[TypingIndicatorManager] = None
        self.message_dispatcher: Optional[MessageDispatcher] = None
        self._initialized = False
        self._closed = False

    async def initialize(self) -> "ServiceContainer":
        """Initialize shared infrastructure exactly once."""
        if self._initialized:
            return self
        self._closed = False

        db_settings = self.settings.db
        if not db_settings.url:
            raise RuntimeError(
                "PostgreSQL configuration is required. Please set DATABASE_URL."
            )

        self.storage = await create_storage(db_settings.url, db_settings.use_pgvector)
        self.conversation_manager = PostgresConversationManager(
            db_settings.url,
            db_settings.use_pgvector,
            storage=self.storage,
        )

        memory_settings = self.settings.memory
        book_settings = self.settings.books
        needs_embeddings = memory_settings.enabled or book_settings.rag_enabled
        self.embedding_model = build_embedding_model(self.settings) if needs_embeddings else None

        if memory_settings.enabled and self.embedding_model:
            from memory.llamaindex.vector_store import PgVectorStore
            from memory.manager import LlamaIndexMemoryManager

            self.memory_vector_store = PgVectorStore(
                db_url=db_settings.url,
                table_name=memory_settings.vector_store_table_name,
                embed_dim=memory_settings.embed_dim,
            )
            self.memory_manager = LlamaIndexMemoryManager(
                vector_store=self.memory_vector_store,
                embedding_model=self.embedding_model,
                expand_neighbors=memory_settings.retrieval_expand_neighbors,
            )
            logger.info("Memory manager initialized in service container.")

        if book_settings.rag_enabled and self.embedding_model:
            from knowledge.manager import BookKnowledgeManager
            from knowledge.store import BookVectorStore

            self.book_vector_store = BookVectorStore(
                db_url=db_settings.url,
                table_name="book_chunks",
                embed_dim=memory_settings.embed_dim,
            )
            self.book_knowledge_manager = BookKnowledgeManager(
                store=self.book_vector_store,
                embedding_model=self.embedding_model,
                expand_neighbors=book_settings.rag_expand_neighbors,
                embed_batch_size=book_settings.embed_batch_size,
            )
            logger.info("Book knowledge manager initialized in service container.")

        queue_settings = self.settings.queue
        self.message_queue_manager = MessageQueueManager(queue_settings.redis_url)
        self.typing_manager = TypingIndicatorManager()
        self.message_dispatcher = MessageDispatcher(
            queue_settings.redis_url,
            queue_settings.max_retries,
            queue_settings.lock_timeout,
            token_resolver=BotTokenResolver(
                self.storage.bots,
                default_token=self.settings.TELEGRAM_TOKEN,
                max_cache_size=50,
            ),
        )

        self._initialized = True
        return self

    def build_prompt_assembler(
        self,
        *,
        personality: str | None = None,
        feature_flags: dict | None = None,
    ) -> PromptAssembler:
        """Create a bot-scoped prompt assembler over shared repositories."""
        if not self.storage:
            raise RuntimeError("ServiceContainer.initialize() must be called first.")

        prompt_settings = self.settings.prompts
        assembler = PromptAssembler(
            message_repo=self.storage.messages,
            memory_manager=self.memory_manager,
            conversation_repo=self.storage.conversations,
            user_repo=self.storage.users,
            user_settings_repo=self.storage.user_settings,
            book_knowledge_manager=self.book_knowledge_manager,
            config={
                "max_memory_items": prompt_settings.max_memory_items,
                "memory_token_budget_ratio": prompt_settings.memory_token_budget_ratio,
                "truncation_length": prompt_settings.truncation_length,
                "include_system_template": prompt_settings.include_system_template,
            },
            app_settings=self.settings,
        )
        if personality is not None:
            assembler.personality = personality
        if feature_flags is not None:
            assembler.feature_flags = feature_flags
        return assembler

    def build_ai_handler(self, bot_config: BotConfig | None = None) -> AIHandler:
        """Create a bot-scoped AI handler using shared prompt services."""
        personality = bot_config.personality if bot_config else self.settings.bot.personality
        feature_flags = bot_config.feature_flags if bot_config else {}
        prompt_assembler = self.build_prompt_assembler(
            personality=personality,
            feature_flags=feature_flags,
        )
        ai_handler = AIHandler(prompt_assembler=prompt_assembler)
        ai_handler.update_personality(personality)
        if bot_config:
            ai_handler.apply_llm_config(bot_config.llm_config)
        return ai_handler

    async def close(self) -> None:
        """Release process-owned resources."""
        if self._closed:
            return
        self._closed = True
        if self.message_dispatcher:
            await self.message_dispatcher.close()
        if self.message_queue_manager:
            await self.message_queue_manager.close()
        if self.typing_manager:
            await self.typing_manager.cleanup()
        if self.memory_vector_store:
            await self.memory_vector_store.close()
        if self.book_vector_store:
            await self.book_vector_store.close()
        if self.storage:
            await self.storage.close()
        self._initialized = False
