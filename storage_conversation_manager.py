"""
PostgreSQL-backed ConversationManager that maintains compatibility with the existing bot interface.

This module provides a drop-in replacement for the in-memory ConversationManager
while using the new PostgreSQL storage system for persistence and scalability.
"""

import logging
import time
import uuid
from typing import Dict, List, Optional
from uuid import UUID

from core.utils import mask_db_url
from settings import settings
from storage import Storage, create_storage
from storage.interfaces import Conversation, Message, MessageLog

logger = logging.getLogger(__name__)

MAX_CONVERSATION_HISTORY = settings.bot.max_conversation_history
PROMPT_REPLY_TOKEN_BUDGET = settings.prompts.reply_token_budget
MAX_CONTEXT_TOKENS = settings.bot.max_context_tokens
RESERVED_TOKENS = settings.bot.reserved_tokens
AVAILABLE_HISTORY_TOKENS = settings.bot.available_history_tokens


class PostgresConversationManager:
    """
    PostgreSQL-backed conversation manager that maintains the same interface as the original.

    This class provides seamless integration with existing bot code while adding:
    - Persistent storage across bot restarts
    - Scalable database backend
    - User and persona management
    - Optional semantic memory search
    """

    def __init__(self, db_url: str, use_pgvector: bool = True, storage: Storage | None = None):
        """
        Initialize the PostgreSQL conversation manager.

        Args:
            db_url: PostgreSQL database URL
            use_pgvector: Whether to enable pgvector for semantic search
        """
        self.db_url = db_url
        self.use_pgvector = use_pgvector
        self.storage: Storage | None = storage
        self._owns_storage = storage is None
        self._conversation_id_cache: dict[tuple[int, uuid.UUID | None], uuid.UUID] = {}

        logger.info("PostgresConversationManager initialized. DB: %s, pgvector: %s",
                   mask_db_url(db_url), use_pgvector)

    async def initialize(self):
        """Initialize the storage connection. Must be called before using the manager."""
        if self.storage is None:
            self.storage = await create_storage(self.db_url, self.use_pgvector)
            self._owns_storage = True
            logger.info("Storage connection initialized successfully")

    async def close(self):
        """Close the storage connection."""
        if self.storage and self._owns_storage:
            await self.storage.close()
            self.storage = None
            logger.info("Storage connection closed")

    async def _ensure_user_and_conversation(self, user_id: int, bot_id: uuid.UUID | None = None) -> Conversation:
        """
        Ensure user and conversation exist, creating them if needed.

        Args:
            user_id: Telegram user ID

        Returns:
            Conversation object for the user
        """
        if not self.storage:
            raise RuntimeError("Storage not initialized. Call initialize() first.")

        # Check cache first
        cache_key = (user_id, bot_id)
        if cache_key in self._conversation_id_cache:
            conversation_id = self._conversation_id_cache[cache_key]
            refreshed_conversation = await self.storage.conversations.get_conversation(str(conversation_id))
            if refreshed_conversation:
                return refreshed_conversation
            del self._conversation_id_cache[cache_key]

        # Check if user exists
        user = await self.storage.users.get_user_by_username(str(user_id))
        if not user:
            # Create new user
            user = await self.storage.users.create_user(
                username=str(user_id),
                extra_data={"telegram_id": user_id, "created_at": time.time()}
            )
            logger.info("Created new user: %s (telegram_id: %d)", user.id, user_id)

        # Check for existing conversation
        conversations = await self.storage.conversations.list_conversations(str(user.id), bot_id=str(bot_id) if bot_id else None)
        if conversations:
            # Use the most recent conversation
            conversation = conversations[0] # Already sorted by creation time DESC
        else:
            # Create new conversation
            conversation = await self.storage.conversations.create_conversation(
                user_id=str(user.id),
                bot_id=str(bot_id) if bot_id else None,
                title=f"Chat with {user.username}",
                extra_data={"auto_created": True}
            )
            logger.info("Created new conversation for user %d", user_id)

        # Cache conversation
        self._conversation_id_cache[cache_key] = conversation.id
        return conversation

    async def save_message_to_history(self, user_id: int, role: str, content: str, bot_id: uuid.UUID | None = None) -> MessageLog:
        """
        Save a message to both message history tables.

        Args:
            user_id: Telegram user ID
            role: Role of the message sender ("user" | "assistant")
            content: The message content

        Returns:
            MessageLog object
        """
        if not self.storage:
            raise RuntimeError("Storage not initialized. Call initialize() first.")

        return await self.storage.message_history.save_message(user_id, role, content, bot_id=bot_id)

    async def add_message_async(self, user_id: int, role: str, content: str, bot_id: uuid.UUID | None = None) -> Message:
        """
        Add a message to the user's conversation history.

        Args:
            user_id: Telegram user ID
            role: Message role ("user" or "assistant")
            content: Message content

        Returns:
            The created Message object
        """
        conversation = await self._ensure_user_and_conversation(user_id, bot_id=bot_id)

        message = await self.storage.messages.append_message(
            conversation_id=str(conversation.id),
            role=role,
            content=content,
            extra_data={"telegram_user_id": user_id}
        )

        # Also save to message history tables
        try:
            await self.save_message_to_history(user_id, role, content, bot_id=bot_id)
        except Exception as e:
            logger.error("Failed to save message to history tables: %s", e)

        logger.info("Added message: user=%d, role=%s, length=%d chars",
                   user_id, role, len(content))
        return message

    async def get_conversation_async(self, user_id: int, bot_id: uuid.UUID | None = None) -> list[dict]:
        """
        Get the conversation history for a user.

        Returns:
            List of message dictionaries in original format
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id, bot_id=bot_id)
            messages = await self.storage.messages.list_messages(
                str(conversation.id),
                limit=MAX_CONVERSATION_HISTORY
            )

            # Convert to original format
            conversation_history = []
            for msg in messages:
                conversation_history.append({
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.created_at.timestamp(),
                    "token_count": msg.token_count
                })

            return conversation_history

        except Exception as e:
            logger.error("Error getting conversation for user %d: %s", user_id, e)
            return []

    async def clear_conversation_async(self, user_id: int, bot_id: uuid.UUID | None = None) -> None:
        """
        Clear conversation history for a user by deleting all messages.

        Args:
            user_id: Telegram user ID
        """
        try:
            # Get the current conversation to delete its messages
            conversation = await self._ensure_user_and_conversation(user_id, bot_id=bot_id)

            # Actually delete all messages from the database
            deleted_count = await self.storage.messages.delete_messages(str(conversation.id))

            logger.info(
                "Clear operation completed for user %d: %d messages deleted from conversation table",
                user_id,
                deleted_count,
            )

            # Remove from cache to clear any cached data
            cache_key = (user_id, bot_id)
            if cache_key in self._conversation_cache:
                del self._conversation_cache[cache_key]

            logger.info("Cleared conversation for user %d", user_id)

        except Exception as e:
            logger.error("Error clearing conversation for user %d: %s", user_id, e)

    async def get_formatted_conversation_async(self, user_id: int, bot_id: uuid.UUID | None = None) -> list[dict]:
        """
        Get conversation formatted for AI API with token management.

        Returns:
            List of messages formatted for AI API within token budget
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id, bot_id=bot_id)
            messages = await self.storage.messages.fetch_recent_messages(
                str(conversation.id),
                token_budget=AVAILABLE_HISTORY_TOKENS
            )

            # Convert to AI API format
            formatted_messages = []
            for msg in messages:
                formatted_messages.append({
                    "role": msg.role,
                    "content": msg.content
                })

            logger.info("Formatted %d messages for user %d using %d tokens",
                       len(formatted_messages), user_id,
                       sum(msg.token_count for msg in messages))

            return formatted_messages

        except Exception as e:
            logger.error("Error formatting conversation for user %d: %s", user_id, e)
            return []

    async def get_user_stats_async(self, user_id: int, bot_id: uuid.UUID | None = None) -> dict:
        """
        Get statistics about user's conversation.

        Returns:
            Dictionary with conversation statistics
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id, bot_id=bot_id)
            messages = await self.storage.messages.list_messages(str(conversation.id))

            total_tokens = sum(msg.token_count for msg in messages)
            user_messages = sum(1 for msg in messages if msg.role == "user")
            bot_messages = sum(1 for msg in messages if msg.role == "assistant")

            return {
                "total_messages": len(messages),
                "user_messages": user_messages,
                "bot_messages": bot_messages,
                "estimated_tokens": total_tokens,
                "max_context_tokens": MAX_CONTEXT_TOKENS,
                "reserved_tokens": RESERVED_TOKENS,
                "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
                "available_tokens": max(0, AVAILABLE_HISTORY_TOKENS - total_tokens),
                "token_usage_percent": (total_tokens / AVAILABLE_HISTORY_TOKENS) * 100 if AVAILABLE_HISTORY_TOKENS else 0,
                "last_message": messages[-1].created_at.timestamp() if messages else None
            }

        except Exception as e:
            logger.error("Error getting user stats for user %d: %s", user_id, e)
            return {
                "total_messages": 0,
                "user_messages": 0,
                "bot_messages": 0,
                "estimated_tokens": 0,
                "max_context_tokens": MAX_CONTEXT_TOKENS,
                "reserved_tokens": RESERVED_TOKENS,
                "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
                "available_tokens": AVAILABLE_HISTORY_TOKENS,
                "token_usage_percent": 0,
                "last_message": None
            }

    async def get_conversation_summary_async(self, user_id: int) -> str:
        """
        Get a summary of the conversation for context preservation.
        """
        try:
            conversation_history = await self.get_conversation_async(user_id)
            if not conversation_history:
                return "No conversation history."

            user_messages = [msg["content"] for msg in conversation_history if msg["role"] == "user"]
            if len(user_messages) <= 3:
                return "Conversation just started."

            # Get last 5 user messages for summary
            summary_parts = []
            for i, msg in enumerate(user_messages[-5:], 1):
                summary_parts.append(f"{i}. {msg[:80]}...")

            return "Recent topics: " + " | ".join(summary_parts)

        except Exception as e:
            logger.error("Error getting conversation summary for user %d: %s", user_id, e)
            return "Error retrieving conversation summary."

    async def debug_conversation_state_async(self, user_id: int, bot_id: uuid.UUID | None = None) -> dict:
        """
        Debug method to show current conversation state.
        """
        try:
            conversation_history = await self.get_conversation_async(user_id, bot_id=bot_id)
            formatted_conversation = await self.get_formatted_conversation_async(user_id, bot_id=bot_id)

            raw_tokens = sum(msg.get("token_count", 0) for msg in conversation_history)
            formatted_tokens = sum(
                self.storage.messages.estimate_tokens(msg["content"])
                for msg in formatted_conversation
            ) if self.storage else 0

            return {
                "raw_conversation_length": len(conversation_history),
                "formatted_conversation_length": len(formatted_conversation),
                "raw_tokens": raw_tokens,
                "formatted_tokens": formatted_tokens,
                "max_context_tokens": MAX_CONTEXT_TOKENS,
                "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
                "last_messages": [
                    {
                        "role": msg.get("role", "unknown"),
                        "content": (msg.get("content", "")[:100] + "...")
                                  if len(msg.get("content", "")) > 100
                                  else msg.get("content", ""),
                        "timestamp": msg.get("timestamp", "N/A")
                    }
                    for msg in conversation_history[-5:]
                ] if conversation_history else [],
                "formatted_messages": [
                    {
                        "role": msg.get("role", "unknown"),
                        "content": (msg.get("content", "")[:100] + "...")
                                  if len(msg.get("content", "")) > 100
                                  else msg.get("content", "")
                    }
                    for msg in formatted_conversation[-5:]
                ] if formatted_conversation else []
            }

        except Exception as e:
            logger.error("Error getting debug state for user %d: %s", user_id, e)
            return {
                "raw_conversation_length": 0,
                "formatted_conversation_length": 0,
                "raw_tokens": 0,
                "formatted_tokens": 0,
                "max_context_tokens": MAX_CONTEXT_TOKENS,
                "available_history_tokens": AVAILABLE_HISTORY_TOKENS,
                "last_messages": [],
            "formatted_messages": []
            }

# Factory function to create PostgreSQL conversation manager
def create_conversation_manager(db_url: str, use_pgvector: bool = True) -> 'PostgresConversationManager':
    """
    Factory function to create PostgreSQL conversation manager.

    Args:
        db_url: Database URL (required)
        use_pgvector: Whether to enable pgvector for semantic search

    Returns:
        PostgreSQL conversation manager instance

    Raises:
        ValueError: If db_url is not provided
    """
    if not db_url:
        raise ValueError("db_url is required - PostgreSQL is the only supported backend")

    return PostgresConversationManager(db_url, use_pgvector)
