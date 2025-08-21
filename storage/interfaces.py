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


@dataclass
class MessageUser:
    """Data class representing a user message"""
    id: UUID
    user_id: UUID
    role: str
    content: str
    created_at: datetime


@dataclass
class Memory:
    """Data class representing a memory entry"""
    id: UUID
    conversation_id: UUID
    memory_type: str
    text: str
    created_at: datetime
    embedding: Optional[List[float]] = None


@dataclass
class Conversation:
    """Data class representing a conversation"""
    id: UUID
    user_id: UUID
    persona_id: UUID
    title: Optional[str]
    extra_data: Dict[str, Any]
    created_at: datetime


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


class MessageRepo(Protocol):
    """Protocol for message repository operations"""
    
    async def append_message(self, conversation_id: str, role: str, content: str, extra_data: Dict[str, Any] = None, token_count: int = 0) -> Message: ...
    
    async def fetch_recent_messages(self, conversation_id: str, token_budget: int) -> List[Message]: ...
    
    async def fetch_messages_since(self, conversation_id: str, since_ts: datetime) -> List[Message]: ...
    
    async def list_messages(self, conversation_id: str, limit: int = 100, offset: int = 0) -> List[Message]: ...
    
    async def delete_messages(self, conversation_id: str) -> int: ...
    
    def estimate_tokens(self, text: str) -> int: ...


class MessageHistoryRepo(Protocol):
    """Protocol for message history repository operations"""
    
    async def save_message(self, user_id: UUID, role: str, content: str) -> tuple[MessageLog, MessageUser]: ...
    
    async def get_user_history(self, user_id: UUID, limit: int = 100) -> List[MessageUser]: ...
    
    async def clear_user_history(self, user_id: UUID) -> int: ...


class MemoryRepo(Protocol):
    """Protocol for memory repository operations"""
    
    async def store_memory(self, conversation_id: str, text: str, embedding: List[float], memory_type: str = "episodic") -> Memory: ...
    
    async def search_memories(self, query_embedding: List[float], top_k: int = 10, similarity_threshold: float = 0.7) -> List[Memory]: ...
    
    async def list_memories(self, conversation_id: str, memory_type: Optional[str] = None) -> List[Memory]: ...


class ConversationRepo(Protocol):
    """Protocol for conversation repository operations"""
    
    async def create_conversation(self, user_id: str, persona_id: str, title: str = None, extra_data: Dict[str, Any] = None) -> Conversation: ...
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]: ...
    
    async def list_conversations(self, user_id: str) -> List[Conversation]: ...
    
    async def update_conversation(self, conversation_id: str, title: str = None, extra_data: Dict[str, Any] = None) -> Optional[Conversation]: ...


class UserRepo(Protocol):
    """Protocol for user repository operations"""
    
    async def create_user(self, username: str, extra_data: Dict[str, Any] = None) -> User: ...
    
    async def get_user(self, user_id: str) -> Optional[User]: ...
    
    async def get_user_by_username(self, username: str) -> Optional[User]: ...


class PersonaRepo(Protocol):
    """Protocol for persona repository operations"""
    
    async def create_persona(self, user_id: str, name: str, config: Dict[str, Any] = None) -> Persona: ...
    
    async def get_persona(self, persona_id: str) -> Optional[Persona]: ...
    
    async def list_personas(self, user_id: str) -> List[Persona]: ...