"""
PromptAssembler for building LLM chat prompts with memory integration.

This module provides the PromptAssembler class that orchestrates building
chat prompts with memory context, conversation history, bot personality,
and proper token budgeting.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from collections.abc import Mapping

from core.tokens import TokenCounter, Tokenizer
from features import BotFeature, has_feature
from settings import AppSettings, build_settings
from storage.interfaces import (
    ConversationRepo,
    MessageRepo,
    UserBotSettingsRepo,
    UserRepo,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from knowledge.manager import BookKnowledgeManager
    from memory.manager import LlamaIndexMemoryManager


class PromptAssembler:
    """
    Main class for assembling LLM chat prompts with memory integration.

    This class orchestrates the process of:
    - Building system prompts with persona configuration
    - Including relevant memories within token budget
    - Adding conversation history within token constraints
    - Proper token accounting and metadata tracking
    """

    def __init__(
        self,
        message_repo: MessageRepo,
        memory_manager: Optional["LlamaIndexMemoryManager"],
        conversation_repo: ConversationRepo,
        user_repo: UserRepo,
        user_settings_repo: UserBotSettingsRepo | None = None,
        book_knowledge_manager: Optional["BookKnowledgeManager"] = None,
        tokenizer: Tokenizer | None = None,
        config: Mapping[str, Any] | None = None,
        app_settings: AppSettings | None = None,
    ):
        """
        Initialize PromptAssembler.

        Args:
            message_repo: Repository for message storage/retrieval
            memory_manager: Manager for memory operations
            conversation_repo: Repository for conversation operations
            user_repo: Repository for user operations
            tokenizer: Optional tokenizer for accurate token counting
            config: Configuration dictionary with:
                - max_memory_items: Maximum memory items to include (default: 3)
                - memory_token_budget_ratio: Ratio of history budget for memories (default: 0.4)
                - truncation_length: Length for message truncation (default: 200)
                - include_system_template: Whether to include base system template (default: True)
        """
        self.message_repo = message_repo
        self.memory_manager = memory_manager
        self.conversation_repo = conversation_repo
        self.user_repo = user_repo
        self.user_settings_repo = user_settings_repo
        self.book_knowledge_manager = book_knowledge_manager
        self.token_counter = TokenCounter(tokenizer)
        self.settings = app_settings or build_settings()
        prompt_settings = self.settings.prompts
        book_settings = self.settings.books
        bot_settings = self.settings.bot

        # Set default config values
        self.config = dict(config or {})
        self.max_memory_items = self.config.get("max_memory_items", prompt_settings.max_memory_items)
        self.memory_token_budget_ratio = self.config.get(
            "memory_token_budget_ratio",
            prompt_settings.memory_token_budget_ratio,
        )
        self.truncation_length = self.config.get("truncation_length", prompt_settings.truncation_length)
        self.include_system_template = self.config.get(
            "include_system_template",
            prompt_settings.include_system_template,
        )
        self.default_reply_token_budget = int(self.config.get(
            "reply_token_budget",
            prompt_settings.reply_token_budget,
        ))
        self.default_history_budget = int(self.config.get("history_budget", prompt_settings.history_budget))
        self.default_personality = self.config.get("bot_personality", bot_settings.personality)
        self.book_rag_enabled = self.config.get("book_rag_enabled", book_settings.rag_enabled)
        self.book_rag_top_k = self.config.get("book_rag_top_k", book_settings.rag_top_k)
        self.book_rag_min_score = self.config.get("book_rag_min_score", book_settings.rag_min_score)
        self.book_rag_token_budget_ratio = self.config.get(
            "book_rag_token_budget_ratio",
            book_settings.rag_token_budget_ratio,
        )
        self.personality: str | None = None  # Dynamic personality for multi-bot support
        self.feature_flags = {}

        logger.info(f"PromptAssembler initialized with max_memory_items={self.max_memory_items}")

    async def build_prompt(
        self,
        conversation_id: str,
        reply_token_budget: int | None = None,
        history_budget: int | None = None,
        user_query: str | None = None
    ) -> list[dict[str, str]]:
        """
        Build a chat prompt for LLM request.

        Args:
            conversation_id: UUID string of the conversation
            reply_token_budget: Tokens reserved for LLM reply (default from config)
            history_budget: Tokens available for history and memories (default from config)
            user_query: Optional current user message for memory retrieval

        Returns:
            List of message dicts with 'role' and 'content' keys, ordered for LLM

        Raises:
            ValueError: If conversation_id is invalid
        """
        # Use config defaults if not provided
        if reply_token_budget is None:
            reply_token_budget = self.default_reply_token_budget
        if history_budget is None:
            history_budget = self.default_history_budget

        messages, _ = await self.build_prompt_and_metadata(
            conversation_id, reply_token_budget, history_budget, user_query
        )
        return messages

    async def _resolve_personality(self, conversation) -> str:
        """Resolve bot personality, preferring per-user overrides when present."""
        personality_to_use = self.personality or self.default_personality

        if self.user_settings_repo and conversation and conversation.bot_id:
            try:
                settings = await self.user_settings_repo.get_settings(
                    str(conversation.user_id),
                    str(conversation.bot_id),
                )
                personality_override = (settings.settings or {}).get("personality_override") if settings else None
                if personality_override:
                    personality_to_use = personality_override
                    logger.info(
                        "Loaded per-user personality override for user_id=%s bot_id=%s",
                        conversation.user_id,
                        conversation.bot_id,
                    )
            except Exception as e:
                logger.warning("Failed to load per-user personality override: %s", e)

        return personality_to_use

    def _build_system_sections(self, personality: str, conversation) -> tuple[list[dict[str, str]], int]:
        """Build system prompt and summary sections."""
        messages = []
        system_tokens = 0

        if self.include_system_template:
            messages.append({"role": "system", "content": personality})
            system_tokens += self.token_counter.count_tokens(personality)
            logger.debug("Added system template: %s tokens", system_tokens)

        if conversation and conversation.summary:
            summary_content = f"This is a summary of the conversation so far:\n{conversation.summary}"
            messages.append({"role": "system", "content": summary_content})
            summary_tokens = self.token_counter.count_tokens(summary_content)
            system_tokens += summary_tokens
            logger.debug("Added conversation summary: %s tokens", summary_tokens)

        return messages, system_tokens

    async def _resolve_memory_query(self, conversation_id: str, conversation, user_query: str | None) -> str | None:
        """Resolve the best query to use for memory retrieval."""
        if user_query:
            logger.debug("Using provided user_query for memory query")
            return user_query

        last_user_message = await self.message_repo.get_last_user_message(conversation_id)
        if last_user_message:
            logger.debug("Using last user message from repo for memory query")
            return last_user_message.content

        if conversation and conversation.summary:
            logger.info("No user query or last user message; using conversation summary for memory query")
            return conversation.summary

        return None

    async def _build_memory_section(
        self,
        conversation_id: str,
        conversation,
        user_query: str | None,
        memory_budget: int,
    ) -> tuple[dict[str, str] | None, int]:
        """Build the semantic memory section, isolated from history assembly."""
        try:
            if not self.memory_manager:
                logger.info("Memory manager not available, skipping semantic search")
                return None, 0
            if not conversation:
                logger.info("No conversation found, skipping memory retrieval")
                return None, 0

            memory_query = await self._resolve_memory_query(conversation_id, conversation, user_query)
            if not memory_query:
                logger.info("No user message or summary available, skipping memory retrieval")
                return None, 0

            user = await self.user_repo.get_user(str(conversation.user_id))
            if not user:
                logger.warning("User not found for conversation %s, skipping memory", conversation_id[:8])
                return None, 0

            logger.info(
                "Querying memory for user=%s, query='%s', bot_id=%s",
                user.username,
                memory_query[:80],
                conversation.bot_id,
            )
            context = await self.memory_manager.get_context(
                user_id=user.username,
                query=memory_query,
                top_k=self.max_memory_items,
                bot_id=str(conversation.bot_id) if conversation.bot_id else None
            )
            if not context:
                logger.info("Semantic search returned no results (empty vector store?)")
                return None, 0

            memory_content = f"### Memory Context\n{context}"
            memory_message_tokens = self.token_counter.count_tokens(memory_content)

            if memory_message_tokens > memory_budget:
                logger.warning(
                    "Memory context (%d tokens) exceeds budget (%d tokens), truncating",
                    memory_message_tokens,
                    memory_budget,
                )
                lines = context.split("\n")
                truncated_context = ""
                current_tokens = self.token_counter.count_tokens("### Memory Context\n")
                for line in lines:
                    line_tokens = self.token_counter.count_tokens(line + "\n")
                    if current_tokens + line_tokens <= memory_budget:
                        truncated_context += line + "\n"
                        current_tokens += line_tokens
                    else:
                        break
                context = truncated_context.strip()
                memory_content = f"### Memory Context\n{context}"
                memory_message_tokens = current_tokens

            if not context:
                logger.warning("Memory context too large even after truncation, skipping")
                return None, 0

            logger.info("Added memories to prompt: %s tokens", memory_message_tokens)
            return {"role": "system", "content": memory_content}, memory_message_tokens
        except ValueError as e:
            logger.warning("Failed to retrieve memories due to a value error: %s", e)
        except Exception as e:
            logger.warning("An unexpected error occurred while retrieving memories: %s", e, exc_info=True)

        return None, 0

    async def _build_book_section(
        self,
        conversation_id: str,
        conversation,
        user_query: str | None,
        book_budget: int,
    ) -> tuple[dict[str, str] | None, int]:
        """Build the book knowledge section, isolated from history assembly."""
        try:
            if not self.book_rag_enabled:
                return None, 0
            if not self.book_knowledge_manager:
                return None, 0
            if not conversation or not conversation.bot_id:
                return None, 0
            if not has_feature(self.feature_flags, BotFeature.BOOK_KNOWLEDGE):
                return None, 0

            query = await self._resolve_memory_query(conversation_id, conversation, user_query)
            if not query:
                return None, 0

            context = await self.book_knowledge_manager.get_context(
                bot_id=str(conversation.bot_id),
                query=query,
                top_k=self.book_rag_top_k,
                min_score=self.book_rag_min_score,
            )
            if not context:
                return None, 0

            book_content = f"### Book Context\n{context}"
            book_tokens = self.token_counter.count_tokens(book_content)
            if book_tokens > book_budget:
                lines = context.split("\n")
                truncated_context = ""
                current_tokens = self.token_counter.count_tokens("### Book Context\n")
                for line in lines:
                    line_tokens = self.token_counter.count_tokens(line + "\n")
                    if current_tokens + line_tokens <= book_budget:
                        truncated_context += line + "\n"
                        current_tokens += line_tokens
                    else:
                        break
                context = truncated_context.strip()
                book_content = f"### Book Context\n{context}"
                book_tokens = current_tokens

            if not context:
                return None, 0

            logger.info("Added book context to prompt: %s tokens", book_tokens)
            return {"role": "system", "content": book_content}, book_tokens
        except Exception as e:
            logger.warning("Failed to retrieve book context: %s", e, exc_info=True)

        return None, 0

    async def _build_history_section(
        self,
        conversation_id: str,
        conversation,
        remaining_history_budget: int,
    ) -> tuple[list[dict[str, str]], int, list[str]]:
        """Build conversation history section within the remaining budget."""
        messages = []
        history_tokens = 0
        truncated_message_ids = []

        try:
            last_summarized_id = conversation.last_summarized_message_id if conversation else None
            recent_messages = await self.message_repo.fetch_active_messages(
                conversation_id, remaining_history_budget, last_summarized_id
            )
            logger.info("Retrieved %s active messages for conversation %s", len(recent_messages), conversation_id)

            for msg in recent_messages:
                content = msg.content
                message_tokens = self.token_counter.count_tokens(content)

                if len(content) > self.truncation_length * 2:
                    content = content[:self.truncation_length] + "... (truncated)"
                    truncated_message_ids.append(str(msg.id))
                    message_tokens = self.token_counter.count_tokens(content)

                messages.append({"role": msg.role, "content": content})
                history_tokens += message_tokens

            logger.debug("Added %s history messages: %s tokens", len(recent_messages), history_tokens)
        except Exception as e:
            logger.warning("Failed to load conversation history: %s", e)

        return messages, history_tokens, truncated_message_ids

    async def build_prompt_and_metadata(
        self,
        conversation_id: str,
        reply_token_budget: int | None = None,
        history_budget: int | None = None,
        user_query: str | None = None
    ) -> tuple[list[dict[str, str]], dict[str, Any]]:
        """
        Build a chat prompt with detailed metadata.

        Args:
            conversation_id: UUID string of the conversation
            reply_token_budget: Tokens reserved for LLM reply (default from config)
            history_budget: Tokens available for history and memories (default from config)
            user_query: Optional current user message for memory retrieval

        Returns:
            Tuple of (messages, metadata) where:
            - messages: List of message dicts ordered for LLM
            - metadata: Dict containing included_memory_ids, token_counts, truncated_message_ids

        Raises:
            ValueError: If inputs are invalid
        """
        # Use config defaults if not provided
        if reply_token_budget is None:
            reply_token_budget = self.default_reply_token_budget
        if history_budget is None:
            history_budget = self.default_history_budget

        if not conversation_id:
            raise ValueError("conversation_id cannot be empty")

        logger.info(f"Building prompt for conversation {conversation_id[:8]}...")

        conversation = await self.conversation_repo.get_conversation(conversation_id)
        personality_to_use = await self._resolve_personality(conversation)

        messages, system_tokens = self._build_system_sections(personality_to_use, conversation)
        token_counts = {
            "system_tokens": system_tokens,
            "memory_tokens": 0,
            "book_tokens": 0,
            "history_tokens": 0,
            "reply_reserved": reply_token_budget
        }

        memory_budget = int(history_budget * self.memory_token_budget_ratio)
        book_budget = int(history_budget * self.book_rag_token_budget_ratio)
        remaining_history_budget = history_budget

        memory_message, memory_tokens = await self._build_memory_section(
            conversation_id,
            conversation,
            user_query,
            memory_budget,
        )
        if memory_message:
            messages.append(memory_message)
            token_counts["memory_tokens"] = memory_tokens
            remaining_history_budget -= memory_tokens

        book_message, book_tokens = await self._build_book_section(
            conversation_id,
            conversation,
            user_query,
            book_budget,
        )
        if book_message:
            messages.append(book_message)
            token_counts["book_tokens"] = book_tokens
            remaining_history_budget -= book_tokens

        history_messages, history_tokens, truncated_message_ids = await self._build_history_section(
            conversation_id,
            conversation,
            remaining_history_budget,
        )
        messages.extend(history_messages)
        token_counts["history_tokens"] = history_tokens

        metadata = {
            "included_memory_ids": [],
            "included_book_chunk_ids": [],
            "token_counts": token_counts,
            "truncated_message_ids": truncated_message_ids,
            "total_tokens": (
                token_counts["system_tokens"]
                + token_counts["memory_tokens"]
                + token_counts["book_tokens"]
                + token_counts["history_tokens"]
            ),
            "conversation_id": conversation_id
        }

        # Log audit information
        logger.info(f"Built prompt with {len(messages)} messages, "
                   f"{1 if memory_message else 0} memory sections, "
                   f"{1 if book_message else 0} book sections, "
                   f"total tokens: {metadata['total_tokens']}")

        return messages, metadata

    async def get_active_message_count(self, conversation_id: str) -> int:
        """
        Get the number of active (unsummarized) messages in a conversation.
        """
        conversation = await self.conversation_repo.get_conversation(conversation_id)
        if not conversation:
            return 0
        return await self.message_repo.count_active_messages(
            conversation_id, conversation.last_summarized_message_id
        )

    def _extract_summary_text(self, memory_text: str) -> str:
        """
        Extract summary text from structured memory data.

        Args:
            memory_text: Raw memory text (potentially JSON)

        Returns:
            Extracted summary text
        """
        if not memory_text:
            return ""

        try:
            if memory_text.startswith('{'):
                import json
                memory_data = json.loads(memory_text)
                return memory_data.get("profile", memory_data.get("summary", memory_text))
            else:
                return memory_text
        except (json.JSONDecodeError, KeyError):
            return memory_text


# Export public API
__all__ = [
    'PromptAssembler',
    'Tokenizer',
    'TokenCounter'
]
