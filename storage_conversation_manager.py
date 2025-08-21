"""
PostgreSQL-backed ConversationManager that maintains compatibility with the existing bot interface.

This module provides a drop-in replacement for the in-memory ConversationManager
while using the new PostgreSQL storage system for persistence and scalability.
"""

import asyncio
import logging
import time
import uuid
from typing import List, Dict, Optional
from uuid import UUID

from config import MAX_CONVERSATION_HISTORY, MAX_TOKENS, MAX_CONTEXT_TOKENS, RESERVED_TOKENS, AVAILABLE_HISTORY_TOKENS
from storage import create_storage, Storage
from storage.interfaces import Message, Conversation, User, Persona, MessageLog, MessageUser

logger = logging.getLogger(__name__)


class PostgresConversationManager:
    """
    PostgreSQL-backed conversation manager that maintains the same interface as the original.
    
    This class provides seamless integration with existing bot code while adding:
    - Persistent storage across bot restarts
    - Scalable database backend
    - User and persona management
    - Optional semantic memory search
    """
    
    def __init__(self, db_url: str, use_pgvector: bool = True):
        """
        Initialize the PostgreSQL conversation manager.
        
        Args:
            db_url: PostgreSQL database URL
            use_pgvector: Whether to enable pgvector for semantic search
        """
        self.db_url = db_url
        self.use_pgvector = use_pgvector
        self.storage: Optional[Storage] = None
        self._user_cache: Dict[int, User] = {}  # Cache for user objects
        self._conversation_cache: Dict[int, Conversation] = {}  # Cache for conversation objects
        self._default_persona_cache: Dict[str, Persona] = {}  # Cache for default personas
        
        logger.info("PostgresConversationManager initialized. DB: %s, pgvector: %s", 
                   self._mask_db_url(db_url), use_pgvector)
    
    async def initialize(self):
        """Initialize the storage connection. Must be called before using the manager."""
        if self.storage is None:
            self.storage = await create_storage(self.db_url, self.use_pgvector)
            logger.info("Storage connection initialized successfully")
    
    async def close(self):
        """Close the storage connection."""
        if self.storage:
            await self.storage.close()
            self.storage = None
            logger.info("Storage connection closed")
    
    async def _ensure_user_and_conversation(self, user_id: int) -> Conversation:
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
        if user_id in self._conversation_cache:
            return self._conversation_cache[user_id]
        
        # Check if user exists
        user = await self.storage.users.get_user_by_username(str(user_id))
        if not user:
            # Create new user
            user = await self.storage.users.create_user(
                username=str(user_id),
                extra_data={"telegram_id": user_id, "created_at": time.time()}
            )
            logger.info("Created new user: %s (telegram_id: %d)", user.id, user_id)
        
        # Cache user
        self._user_cache[user_id] = user
        
        # Check for existing conversation
        conversations = await self.storage.conversations.list_conversations(str(user.id))
        if conversations:
            # Use the most recent conversation
            conversation = conversations[0] # Already sorted by creation time DESC
        else:
            # Create default persona if needed
            personas = await self.storage.personas.list_personas(str(user.id))
            if not personas:
                persona = await self.storage.personas.create_persona(
                    user_id=str(user.id),
                    name="Default Assistant",
                    config={"personality": "caring and affectionate AI girlfriend"}
                )
                logger.info("Created default persona for user %d", user_id)
            else:
                persona = personas[0]
            
            # Create new conversation
            conversation = await self.storage.conversations.create_conversation(
                user_id=str(user.id),
                persona_id=str(persona.id),
                title=f"Chat with {user.username}",
                extra_data={"auto_created": True}
            )
            logger.info("Created new conversation for user %d", user_id)
        
        # Cache conversation
        self._conversation_cache[user_id] = conversation
        return conversation
    
    # Public async methods for direct use from async contexts
    async def get_conversation_async(self, user_id: int) -> List[Dict]:
        """Get conversation history for a user (async version)."""
        return await self._get_conversation_async(user_id)
    
    async def get_formatted_conversation_async(self, user_id: int) -> List[Dict]:
        """Get formatted conversation for AI API (async version)."""
        return await self._get_formatted_conversation_async(user_id)
    
    async def get_user_stats_async(self, user_id: int) -> Dict:
        """Get user statistics (async version)."""
        return await self._get_user_stats_async(user_id)
    
    async def debug_conversation_state_async(self, user_id: int) -> Dict:
        """Debug conversation state (async version)."""
        return await self._debug_conversation_state_async(user_id)
    
    async def clear_conversation_async(self, user_id: int) -> None:
        """Clear conversation history for a user (async version)."""
        await self._clear_conversation_async(user_id)
    
    async def save_message_to_history(self, user_id: int, role: str, content: str) -> tuple[MessageLog, MessageUser]:
        """
        Save a message to both message history tables.
        
        Args:
            user_id: Telegram user ID
            role: Role of the message sender ("user" | "assistant")
            content: The message content
            
        Returns:
            Tuple of (MessageLog, MessageUser) objects
        """
        if not self.storage:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        
        # Convert Telegram user ID (integer) to UUID for the database
        # We'll use a consistent UUID namespace for Telegram user IDs
        user_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"telegram_user_{user_id}")
        
        return await self.storage.message_history.save_message(user_uuid, role, content)
    
    async def get_user_history(self, user_id: int, limit: int = 100) -> List[MessageUser]:
        """
        Get user message history from messages_user table.
        
        Args:
            user_id: Telegram user ID
            limit: Maximum number of messages to return
            
        Returns:
            List of MessageUser objects ordered by creation time
        """
        if not self.storage:
            raise RuntimeError("Storage not initialized. Call initialize() first.")
        
        # Convert Telegram user ID (integer) to UUID for the database
        user_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"telegram_user_{user_id}")
        
        return await self.storage.message_history.get_user_history(user_uuid, limit)
    
    def add_message(self, user_id: int, role: str, content: str) -> None:
        """
        Add a message to the user's conversation history (sync wrapper for async).
        
        This method maintains compatibility with the existing sync interface.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an async context, schedule the task
                asyncio.create_task(self._add_message_async(user_id, role, content))
            else:
                # If not in async context, run it
                asyncio.run(self._add_message_async(user_id, role, content))
        except RuntimeError:
            # No event loop, create one
            asyncio.run(self._add_message_async(user_id, role, content))
    
    async def _add_message_async(self, user_id: int, role: str, content: str) -> Message:
        """
        Add a message to the user's conversation history (async implementation).
        
        Args:
            user_id: Telegram user ID
            role: Message role ("user" or "assistant")
            content: Message content
            
        Returns:
            The created Message object
        """
        conversation = await self._ensure_user_and_conversation(user_id)
        
        message = await self.storage.messages.append_message(
            conversation_id=str(conversation.id),
            role=role,
            content=content,
            extra_data={"telegram_user_id": user_id}
        )
        
        # Also save to message history tables
        try:
            await self.save_message_to_history(user_id, role, content)
        except Exception as e:
            logger.error("Failed to save message to history tables: %s", e)
        
        logger.info("Added message: user=%d, role=%s, length=%d chars", 
                   user_id, role, len(content))
        return message
    
    def get_conversation(self, user_id: int) -> List[Dict]:
        """
        Get the conversation history for a user (sync wrapper).
        
        WARNING: This method should not be called from async contexts.
        Use get_conversation_async() instead from async code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.error("get_conversation called from async context for user %d - use get_conversation_async() instead", user_id)
                return []
            else:
                return asyncio.run(self._get_conversation_async(user_id))
        except RuntimeError:
            # No event loop, create one
            return asyncio.run(self._get_conversation_async(user_id))
        except Exception as e:
            logger.error("Error in get_conversation for user %d: %s", user_id, e)
            return []
    
    async def _get_conversation_async(self, user_id: int) -> List[Dict]:
        """
        Get the conversation history for a user (async implementation).
        
        Returns:
            List of message dictionaries in original format
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id)
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
    
    def clear_conversation(self, user_id: int) -> None:
        """
        Clear conversation history for a user (sync wrapper).
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._clear_conversation_async(user_id))
            else:
                asyncio.run(self._clear_conversation_async(user_id))
        except RuntimeError:
            asyncio.run(self._clear_conversation_async(user_id))
    
    async def _clear_conversation_async(self, user_id: int) -> None:
        """
        Clear conversation history for a user by deleting all messages.
        
        Args:
            user_id: Telegram user ID
        """
        try:
            # Get the current conversation to delete its messages
            conversation = await self._ensure_user_and_conversation(user_id)
            
            # Actually delete all messages from the database
            deleted_count = await self.storage.messages.delete_messages(str(conversation.id))
            
            # Also clear messages from messages_user table and get the count
            # Convert Telegram user ID (integer) to UUID for the database
            user_uuid = uuid.uuid5(uuid.NAMESPACE_OID, f"telegram_user_{user_id}")
            user_history_deleted_count = await self.storage.message_history.clear_user_history(user_uuid)
            
            # Log a single consolidated message with both counts
            logger.info("Clear operation completed for user %d: %d messages deleted from conversation table, %d messages deleted from user history table", 
                       user_id, deleted_count, user_history_deleted_count)
            
            # Remove from cache to clear any cached data
            if user_id in self._conversation_cache:
                del self._conversation_cache[user_id]
            
            logger.info("Cleared conversation for user %d", user_id)
            
        except Exception as e:
            logger.error("Error clearing conversation for user %d: %s", user_id, e)
    
    def get_formatted_conversation(self, user_id: int) -> List[Dict]:
        """
        Get conversation formatted for AI API with token management (sync wrapper).
        
        WARNING: This method should not be called from async contexts.
        Use get_formatted_conversation_async() instead from async code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.error("get_formatted_conversation called from async context for user %d - use get_formatted_conversation_async() instead", user_id)
                return []
            else:
                return asyncio.run(self._get_formatted_conversation_async(user_id))
        except RuntimeError:
            return asyncio.run(self._get_formatted_conversation_async(user_id))
        except Exception as e:
            logger.error("Error in get_formatted_conversation for user %d: %s", user_id, e)
            return []
    
    async def _get_formatted_conversation_async(self, user_id: int) -> List[Dict]:
        """
        Get conversation formatted for AI API with token management (async implementation).
        
        Returns:
            List of messages formatted for AI API within token budget
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id)
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
    
    def get_user_stats(self, user_id: int) -> Dict:
        """
        Get statistics about user's conversation (sync wrapper).
        
        WARNING: This method should not be called from async contexts.
        Use get_user_stats_async() instead from async code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.error("get_user_stats called from async context for user %d - use get_user_stats_async() instead", user_id)
                return {"total_messages": 0, "user_messages": 0, "bot_messages": 0, "estimated_tokens": 0}
            else:
                return asyncio.run(self._get_user_stats_async(user_id))
        except RuntimeError:
            return asyncio.run(self._get_user_stats_async(user_id))
        except Exception as e:
            logger.error("Error in get_user_stats for user %d: %s", user_id, e)
            return {"total_messages": 0, "user_messages": 0, "bot_messages": 0, "estimated_tokens": 0}
    
    async def _get_user_stats_async(self, user_id: int) -> Dict:
        """
        Get statistics about user's conversation (async implementation).
        
        Returns:
            Dictionary with conversation statistics
        """
        try:
            conversation = await self._ensure_user_and_conversation(user_id)
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
    
    def get_conversation_summary(self, user_id: int) -> str:
        """
        Get a summary of the conversation for context preservation (sync wrapper).
        """
        return asyncio.run(self._get_conversation_summary_async(user_id))
    
    async def _get_conversation_summary_async(self, user_id: int) -> str:
        """
        Get a summary of the conversation for context preservation (async implementation).
        """
        try:
            conversation_history = await self._get_conversation_async(user_id)
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
    
    def debug_conversation_state(self, user_id: int) -> Dict:
        """
        Debug method to show current conversation state (sync wrapper).
        
        WARNING: This method should not be called from async contexts.
        Use debug_conversation_state_async() instead from async code.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                logger.error("debug_conversation_state called from async context for user %d - use debug_conversation_state_async() instead", user_id)
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
            else:
                return asyncio.run(self._debug_conversation_state_async(user_id))
        except RuntimeError:
            return asyncio.run(self._debug_conversation_state_async(user_id))
        except Exception as e:
            logger.error("Error in debug_conversation_state for user %d: %s", user_id, e)
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
    
    async def _debug_conversation_state_async(self, user_id: int) -> Dict:
        """
        Debug method to show current conversation state (async implementation).
        """
        try:
            conversation_history = await self._get_conversation_async(user_id)
            formatted_conversation = await self._get_formatted_conversation_async(user_id)
            
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
    
    def _mask_db_url(self, db_url: str) -> str:
        """Mask sensitive parts of database URL for logging."""
        try:
            if '@' in db_url and '://' in db_url:
                scheme_and_auth, rest = db_url.split('://', 1)
                if '@' in rest:
                    auth, host_and_path = rest.split('@', 1)
                    if ':' in auth:
                        user, _ = auth.split(':', 1)
                        return f"{scheme_and_auth}://{user}:***@{host_and_path}"
            return db_url[:20] + "***"
        except Exception:
            return "***masked***"


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