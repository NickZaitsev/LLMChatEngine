"""Typed repository contracts and DTOs for storage implementations."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol
from uuid import UUID

TelegramUserId = int


@dataclass
class Message:
    """Data class representing a message"""
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    extra_data: dict[str, Any]
    token_count: int
    created_at: datetime


@dataclass
class MessageLog:
    """Data class representing a message log entry.

    `user_id` is the internal UUID stored by `messages_log`. Runtime callers
    identify Telegram users by their raw integer ID; the repository owns the
    deterministic conversion used by this analytics table.
    """
    id: UUID
    user_id: UUID
    role: str
    content: str
    created_at: datetime
    bot_id: UUID | None = None


@dataclass
class Conversation:
    """Data class representing a conversation"""
    id: UUID
    user_id: UUID
    persona_id: UUID | None
    title: str | None
    extra_data: dict[str, Any]
    created_at: datetime
    bot_id: UUID | None = None
    summary: str | None = None
    last_summarized_message_id: UUID | None = None
    last_memorized_message_id: UUID | None = None


@dataclass
class User:
    """Data class representing a user"""
    id: UUID
    username: str
    extra_data: dict[str, Any]


@dataclass
class Persona:
    """Data class representing a persona"""
    id: UUID
    user_id: UUID
    name: str
    config: dict[str, Any]


@dataclass
class Bot:
    """Data class representing a bot configuration"""
    id: UUID
    token_encrypted: str
    name: str
    personality: str
    is_active: bool
    feature_flags: dict[str, Any]
    llm_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class Book:
    """Data class representing uploaded book metadata."""
    id: UUID
    bot_id: UUID
    title: str
    author: str | None
    source_filename: str
    file_format: str
    file_hash: str
    status: str
    error: str | None
    chunk_count: int
    char_count: int
    created_at: datetime
    updated_at: datetime


@dataclass
class UserBotSettings:
    """Data class representing per-user per-bot settings"""
    id: UUID
    user_id: UUID
    bot_id: UUID
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MessageRepo(Protocol):
    """Protocol for message repository operations"""
    
    async def append_message(self, conversation_id: str, role: str, content: str, extra_data: dict[str, Any] | None = None, token_count: int = 0) -> Message:
        """Persist a message in a conversation."""
        ...
    
    async def fetch_recent_messages(self, conversation_id: str, token_budget: int) -> list[Message]:
        """Fetch recent messages constrained by token budget."""
        ...
    
    async def fetch_messages_since(self, conversation_id: str, since_ts: datetime) -> list[Message]:
        """Fetch messages created after a timestamp."""
        ...
    
    async def list_messages(self, conversation_id: str, limit: int = 100, offset: int = 0) -> list[Message]:
        """List messages for a conversation with pagination."""
        ...
    
    async def delete_messages(self, conversation_id: str) -> int:
        """Delete messages for a conversation and return the count."""
        ...

    async def count_active_messages(self, conversation_id: str, last_summarized_message_id: UUID | None) -> int:
        """Count messages not covered by the latest summary."""
        ...

    async def fetch_active_messages(self, conversation_id: str, token_budget: int, last_summarized_message_id: UUID | None) -> list[Message]:
        """Fetch unsummarized messages constrained by token budget."""
        ...

    async def get_messages_for_summary(self, conversation_id: str, last_summarized_message_id: UUID | None) -> list[Message]:
        """Fetch unsummarized messages for summary generation."""
        ...
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        ...


class MessageHistoryRepo(Protocol):
    """Protocol for message history repository operations"""
    
    async def save_message(self, user_id: TelegramUserId, role: str, content: str, bot_id: UUID | None = None) -> MessageLog:
        """Persist a message log entry for a raw Telegram user ID."""
        ...


class ConversationRepo(Protocol):
    """Protocol for conversation repository operations"""
    
    async def create_conversation(self, user_id: str, persona_id: str | None = None, bot_id: str | None = None, title: str | None = None, extra_data: dict[str, Any] | None = None) -> Conversation:
        """Create a conversation record."""
        ...
    
    async def get_conversation(self, conversation_id: str) -> Conversation | None:
        """Fetch a conversation by ID."""
        ...
    
    async def list_conversations(self, user_id: str, bot_id: str | None = None) -> list[Conversation]:
        """List conversations for a user and optional bot."""
        ...

    async def count_users_for_bot(self, bot_id: str) -> int:
        """Count distinct users with conversations for a bot."""
        ...
    
    async def update_conversation(self, conversation_id: str, title: str | None = None, extra_data: dict[str, Any] | None = None, summary: str | None = None, last_summarized_message_id: UUID | None = None, last_memorized_message_id: UUID | None = None) -> Conversation | None:
        """Update conversation metadata and summary fields."""
        ...


class UserRepo(Protocol):
    """Protocol for user repository operations"""
    
    async def create_user(self, username: str, extra_data: dict[str, Any] | None = None) -> User:
        """Create a user record."""
        ...
    
    async def get_user(self, user_id: str) -> User | None:
        """Fetch a user by ID."""
        ...
    
    async def get_user_by_username(self, username: str) -> User | None:
        """Fetch a user by username."""
        ...


class PersonaRepo(Protocol):
    """Protocol for persona repository operations"""
    
    async def create_persona(self, user_id: str, name: str, config: dict[str, Any] | None = None) -> Persona:
        """Create a persona record."""
        ...
    
    async def get_persona(self, persona_id: str) -> Persona | None:
        """Fetch a persona by ID."""
        ...
    
    async def list_personas(self, user_id: str) -> list[Persona]:
        """List personas owned by a user."""
        ...


class BotRepo(Protocol):
    """Protocol for bot repository operations"""
    
    async def create_bot(self, token_encrypted: str, name: str, personality: str, feature_flags: dict[str, Any] | None = None, llm_config: dict[str, Any] | None = None) -> Bot:
        """Create a managed bot record."""
        ...
    
    async def get_bot(self, bot_id: str) -> Bot | None:
        """Fetch a managed bot by ID."""
        ...
    
    async def list_bots(self, is_active: bool | None = None) -> list[Bot]:
        """List managed bots with optional active filtering."""
        ...
    
    async def update_bot(self, bot_id: str, name: str | None = None, personality: str | None = None, is_active: bool | None = None, feature_flags: dict[str, Any] | None = None, llm_config: dict[str, Any] | None = None) -> Bot | None:
        """Update a managed bot record."""
        ...

    async def update_personality(self, bot_id: str, personality: str) -> Bot | None:
        """Update a bot personality prompt."""
        ...

    async def update_flags(self, bot_id: str, feature_flags: dict[str, Any]) -> Bot | None:
        """Replace a bot feature flag dictionary."""
        ...

    async def set_active(self, bot_id: str, is_active: bool) -> Bot | None:
        """Set whether a bot is active."""
        ...

    async def get_personality_and_flags(self, bot_id: str) -> tuple[str, dict[str, Any]] | None:
        """Fetch prompt-time bot settings."""
        ...
    
    async def delete_bot(self, bot_id: str) -> bool:
        """Delete or deactivate a managed bot."""
        ...


class BookRepo(Protocol):
    """Protocol for book metadata repository operations."""

    async def create_book(self, bot_id: str, title: str, author: str | None, source_filename: str, file_format: str, file_hash: str) -> Book:
        """Create a pending book metadata row."""
        ...

    async def get_book(self, book_id: str) -> Book | None:
        """Fetch a book by ID."""
        ...

    async def list_books(self, bot_id: str) -> list[Book]:
        """List books attached to a bot."""
        ...

    async def update_status(self, book_id: str, status: str, error: str | None = None, chunk_count: int | None = None, char_count: int | None = None) -> Book | None:
        """Update ingestion status and optional counters."""
        ...

    async def update_metadata(self, book_id: str, title: str, author: str | None) -> Book | None:
        """Update human-facing book metadata."""
        ...

    async def delete_book(self, book_id: str) -> bool:
        """Delete a book metadata row."""
        ...

    async def find_by_hash(self, bot_id: str, file_hash: str) -> Book | None:
        """Find an existing book upload by bot and file hash."""
        ...


class UserBotSettingsRepo(Protocol):
    """Protocol for user bot settings repository operations"""
    
    async def get_or_create_settings(self, user_id: str, bot_id: str) -> UserBotSettings:
        """Fetch settings or create defaults for a user and bot."""
        ...
    
    async def get_settings(self, user_id: str, bot_id: str) -> UserBotSettings | None:
        """Fetch settings for a user and bot."""
        ...
    
    async def update_settings(self, user_id: str, bot_id: str, settings: dict[str, Any]) -> UserBotSettings:
        """Merge and persist settings for a user and bot."""
        ...
