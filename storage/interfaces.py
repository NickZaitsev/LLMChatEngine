"""Typed repository contracts and DTOs for storage implementations."""

from typing import Protocol, List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass
from uuid import UUID


@dataclass
class Message:
    """Data class representing a message"""
    id: UUID
    conversation_id: UUID
    role: str
    content: str
    extra_data: Dict[str, Any]
    token_count: int
    created_at: datetime


@dataclass
class MessageLog:
    """Data class representing a message log entry"""
    id: UUID
    user_id: UUID
    role: str
    content: str
    created_at: datetime
    bot_id: Optional[UUID] = None


@dataclass
class MessageUser:
    """Data class representing a user message"""
    id: UUID
    user_id: UUID
    role: str
    content: str
    created_at: datetime
    bot_id: Optional[UUID] = None


@dataclass
class Conversation:
    """Data class representing a conversation"""
    id: UUID
    user_id: UUID
    persona_id: UUID
    title: Optional[str]
    extra_data: Dict[str, Any]
    created_at: datetime
    bot_id: Optional[UUID] = None
    summary: Optional[str] = None
    last_summarized_message_id: Optional[UUID] = None
    last_memorized_message_id: Optional[UUID] = None


@dataclass
class User:
    """Data class representing a user"""
    id: UUID
    username: str
    extra_data: Dict[str, Any]


@dataclass
class Persona:
    """Data class representing a persona"""
    id: UUID
    user_id: UUID
    name: str
    config: Dict[str, Any]


@dataclass
class Bot:
    """Data class representing a bot configuration"""
    id: UUID
    token_encrypted: str
    name: str
    personality: str
    is_active: bool
    feature_flags: Dict[str, Any]
    llm_config: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class Book:
    """Data class representing uploaded book metadata."""
    id: UUID
    bot_id: UUID
    title: str
    author: Optional[str]
    source_filename: str
    file_format: str
    file_hash: str
    status: str
    error: Optional[str]
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
    settings: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MessageRepo(Protocol):
    """Protocol for message repository operations"""
    
    async def append_message(self, conversation_id: str, role: str, content: str, extra_data: Optional[Dict[str, Any]] = None, token_count: int = 0) -> Message:
        """Persist a message in a conversation."""
        ...
    
    async def fetch_recent_messages(self, conversation_id: str, token_budget: int) -> List[Message]:
        """Fetch recent messages constrained by token budget."""
        ...
    
    async def fetch_messages_since(self, conversation_id: str, since_ts: datetime) -> List[Message]:
        """Fetch messages created after a timestamp."""
        ...
    
    async def list_messages(self, conversation_id: str, limit: int = 100, offset: int = 0) -> List[Message]:
        """List messages for a conversation with pagination."""
        ...
    
    async def delete_messages(self, conversation_id: str) -> int:
        """Delete messages for a conversation and return the count."""
        ...

    async def count_active_messages(self, conversation_id: str, last_summarized_message_id: Optional[UUID]) -> int:
        """Count messages not covered by the latest summary."""
        ...

    async def fetch_active_messages(self, conversation_id: str, token_budget: int, last_summarized_message_id: Optional[UUID]) -> List[Message]:
        """Fetch unsummarized messages constrained by token budget."""
        ...

    async def get_messages_for_summary(self, conversation_id: str, last_summarized_message_id: Optional[UUID]) -> List[Message]:
        """Fetch unsummarized messages for summary generation."""
        ...
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        ...


class MessageHistoryRepo(Protocol):
    """Protocol for message history repository operations"""
    
    async def save_message(self, user_id: UUID, role: str, content: str, bot_id: Optional[UUID] = None) -> tuple[MessageLog, MessageUser]:
        """Persist a user-facing message history entry."""
        ...
    
    async def get_user_history(self, user_id: UUID, limit: int = 100, bot_id: Optional[UUID] = None) -> List[MessageUser]:
        """Fetch recent user-facing history."""
        ...
    
    async def clear_user_history(self, user_id: UUID, bot_id: Optional[UUID] = None) -> int:
        """Delete user-facing history and return the count."""
        ...


class ConversationRepo(Protocol):
    """Protocol for conversation repository operations"""
    
    async def create_conversation(self, user_id: str, persona_id: str, bot_id: Optional[str] = None, title: Optional[str] = None, extra_data: Optional[Dict[str, Any]] = None) -> Conversation:
        """Create a conversation record."""
        ...
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Fetch a conversation by ID."""
        ...
    
    async def list_conversations(self, user_id: str, bot_id: Optional[str] = None) -> List[Conversation]:
        """List conversations for a user and optional bot."""
        ...
    
    async def update_conversation(self, conversation_id: str, title: Optional[str] = None, extra_data: Optional[Dict[str, Any]] = None, summary: Optional[str] = None, last_summarized_message_id: Optional[UUID] = None, last_memorized_message_id: Optional[UUID] = None) -> Optional[Conversation]:
        """Update conversation metadata and summary fields."""
        ...


class UserRepo(Protocol):
    """Protocol for user repository operations"""
    
    async def create_user(self, username: str, extra_data: Optional[Dict[str, Any]] = None) -> User:
        """Create a user record."""
        ...
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Fetch a user by ID."""
        ...
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """Fetch a user by username."""
        ...


class PersonaRepo(Protocol):
    """Protocol for persona repository operations"""
    
    async def create_persona(self, user_id: str, name: str, config: Optional[Dict[str, Any]] = None) -> Persona:
        """Create a persona record."""
        ...
    
    async def get_persona(self, persona_id: str) -> Optional[Persona]:
        """Fetch a persona by ID."""
        ...
    
    async def list_personas(self, user_id: str) -> List[Persona]:
        """List personas owned by a user."""
        ...


class BotRepo(Protocol):
    """Protocol for bot repository operations"""
    
    async def create_bot(self, token_encrypted: str, name: str, personality: str, feature_flags: Optional[Dict[str, Any]] = None, llm_config: Optional[Dict[str, Any]] = None) -> Bot:
        """Create a managed bot record."""
        ...
    
    async def get_bot(self, bot_id: str) -> Optional[Bot]:
        """Fetch a managed bot by ID."""
        ...
    
    async def list_bots(self, is_active: Optional[bool] = None) -> List[Bot]:
        """List managed bots with optional active filtering."""
        ...
    
    async def update_bot(self, bot_id: str, name: Optional[str] = None, personality: Optional[str] = None, is_active: Optional[bool] = None, feature_flags: Optional[Dict[str, Any]] = None, llm_config: Optional[Dict[str, Any]] = None) -> Optional[Bot]:
        """Update a managed bot record."""
        ...

    async def update_personality(self, bot_id: str, personality: str) -> Optional[Bot]:
        """Update a bot personality prompt."""
        ...

    async def update_flags(self, bot_id: str, feature_flags: Dict[str, Any]) -> Optional[Bot]:
        """Replace a bot feature flag dictionary."""
        ...

    async def set_active(self, bot_id: str, is_active: bool) -> Optional[Bot]:
        """Set whether a bot is active."""
        ...

    async def get_personality_and_flags(self, bot_id: str) -> Optional[tuple[str, Dict[str, Any]]]:
        """Fetch prompt-time bot settings."""
        ...
    
    async def delete_bot(self, bot_id: str) -> bool:
        """Delete or deactivate a managed bot."""
        ...


class BookRepo(Protocol):
    """Protocol for book metadata repository operations."""

    async def create_book(self, bot_id: str, title: str, author: Optional[str], source_filename: str, file_format: str, file_hash: str) -> Book:
        """Create a pending book metadata row."""
        ...

    async def get_book(self, book_id: str) -> Optional[Book]:
        """Fetch a book by ID."""
        ...

    async def list_books(self, bot_id: str) -> List[Book]:
        """List books attached to a bot."""
        ...

    async def update_status(self, book_id: str, status: str, error: Optional[str] = None, chunk_count: Optional[int] = None, char_count: Optional[int] = None) -> Optional[Book]:
        """Update ingestion status and optional counters."""
        ...

    async def delete_book(self, book_id: str) -> bool:
        """Delete a book metadata row."""
        ...

    async def find_by_hash(self, bot_id: str, file_hash: str) -> Optional[Book]:
        """Find an existing book upload by bot and file hash."""
        ...


class UserBotSettingsRepo(Protocol):
    """Protocol for user bot settings repository operations"""
    
    async def get_or_create_settings(self, user_id: str, bot_id: str) -> UserBotSettings:
        """Fetch settings or create defaults for a user and bot."""
        ...
    
    async def get_settings(self, user_id: str, bot_id: str) -> Optional[UserBotSettings]:
        """Fetch settings for a user and bot."""
        ...
    
    async def update_settings(self, user_id: str, bot_id: str, settings: Dict[str, Any]) -> UserBotSettings:
        """Merge and persist settings for a user and bot."""
        ...
