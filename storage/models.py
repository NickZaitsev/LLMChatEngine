"""
SQLAlchemy models for the AI girlfriend bot storage system.

This module defines the database schema using SQLAlchemy 2.x with async support.
Includes optional pgvector support for semantic memory search.
"""

import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey, func, Index, JSON
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import expression

# Try to import pgvector, but handle gracefully if not available
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    # Fallback for systems without pgvector
    PGVECTOR_AVAILABLE = False
    Vector = None


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models with async support"""
    pass


class User(Base):
    """
    User model representing system users.
    
    Attributes:
        id: Unique identifier for the user
        username: Unique username for the user
        extra_data: Additional user data stored as JSON
    """
    __tablename__ = 'users'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the user"
    )
    username: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        doc="Unique username for the user"
    )
    extra_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Additional user data stored as JSON"
    )
    
    # Relationships
    personas: Mapped[List["Persona"]] = relationship(
        "Persona", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", 
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}')>"


class Persona(Base):
    """
    Persona model representing different AI personalities.
    
    Attributes:
        id: Unique identifier for the persona
        user_id: Foreign key reference to the owning user
        name: Display name of the persona
        config: Persona configuration stored as JSON
    """
    __tablename__ = 'personas'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the persona"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('users.id', ondelete='CASCADE'), 
        nullable=False,
        doc="Foreign key reference to the owning user"
    )
    name: Mapped[str] = mapped_column(
        String(255), 
        nullable=False,
        doc="Display name of the persona"
    )
    config: Mapped[Dict[str, Any]] = mapped_column(
        JSON, 
        nullable=False, 
        default=dict,
        doc="Persona configuration stored as JSON"
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="personas")
    conversations: Mapped[List["Conversation"]] = relationship(
        "Conversation", 
        back_populates="persona",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Persona(id={self.id}, name='{self.name}', user_id={self.user_id})>"


class Conversation(Base):
    """
    Conversation model representing chat sessions.
    
    Attributes:
        id: Unique identifier for the conversation
        user_id: Foreign key reference to the user
        persona_id: Foreign key reference to the persona
        title: Optional title for the conversation
        metadata: Additional conversation metadata stored as JSON
        created_at: Timestamp when the conversation was created
    """
    __tablename__ = 'conversations'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the conversation"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('users.id', ondelete='CASCADE'), 
        nullable=False,
        doc="Foreign key reference to the user"
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('personas.id', ondelete='CASCADE'), 
        nullable=False,
        doc="Foreign key reference to the persona"
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        doc="Optional title for the conversation"
    )
    extra_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Additional conversation data stored as JSON"
    )
    summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        doc="The latest summary of the conversation"
    )
    last_summarized_message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('messages.id', ondelete='SET NULL'),
        nullable=True,
        doc="ID of the last message included in the summary"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=func.now(),
        doc="Timestamp when the conversation was created"
    )
    
    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="conversations")
    persona: Mapped["Persona"] = relationship("Persona", back_populates="conversations")
    messages: Mapped[List["Message"]] = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
        foreign_keys="[Message.conversation_id]"
    )
    memories: Mapped[List["Memory"]] = relationship(
        "Memory", 
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    
    last_summarized_message: Mapped[Optional["Message"]] = relationship(
        "Message",
        foreign_keys=[last_summarized_message_id]
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title='{self.title}', user_id={self.user_id})>"


class Message(Base):
    """
    Message model representing individual chat messages.
    
    Attributes:
        id: Unique identifier for the message
        conversation_id: Foreign key reference to the conversation
        role: Role of the message sender ("user" | "assistant" | "system")
        content: The message content text
        metadata: Additional message metadata stored as JSON
        token_count: Estimated token count for the message
        created_at: Timestamp when the message was created
    """
    __tablename__ = 'messages'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the message"
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('conversations.id', ondelete='CASCADE'), 
        nullable=False,
        doc="Foreign key reference to the conversation"
    )
    role: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        doc="Role of the message sender (user|assistant|system)"
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        doc="The message content text"
    )
    extra_data: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        doc="Additional message data stored as JSON"
    )
    token_count: Mapped[int] = mapped_column(
        Integer, 
        nullable=False, 
        default=0,
        doc="Estimated token count for the message"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=func.now(),
        doc="Timestamp when the message was created"
    )
    
    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation",
        back_populates="messages",
        foreign_keys=[conversation_id]
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('ix_messages_conversation_created_at', 'conversation_id', 'created_at'),
        Index('ix_messages_conversation_role', 'conversation_id', 'role'),
    )
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<Message(id={self.id}, role='{self.role}', content='{content_preview}')>"


class MessageLog(Base):
    """
    MessageLog model representing permanent message logs for analytics/debugging.
    
    Attributes:
        id: Unique identifier for the message log entry
        user_id: Telegram user ID (as UUID to match existing schema)
        role: Role of the message sender ("user" | "bot")
        content: The message content text
        created_at: Timestamp when the message was created
    """
    __tablename__ = 'messages_log'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the message log entry"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=False,
        doc="Telegram user ID"
    )
    role: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        doc="Role of the message sender (user|bot)"
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        doc="The message content text"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=func.now(),
        doc="Timestamp when the message was created"
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('ix_messages_log_user_id', 'user_id'),
        Index('ix_messages_log_created_at', 'created_at'),
    )
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<MessageLog(id={self.id}, user_id={self.user_id}, role='{self.role}', content='{content_preview}')>"


class MessageUser(Base):
    """
    MessageUser model representing active conversation history for each user.
    
    Attributes:
        id: Unique identifier for the message
        user_id: Telegram user ID (as UUID to match existing schema)
        role: Role of the message sender ("user" | "bot")
        content: The message content text
        created_at: Timestamp when the message was created
    """
    __tablename__ = 'messages_user'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the message"
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=False,
        doc="Telegram user ID"
    )
    role: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        doc="Role of the message sender (user|bot)"
    )
    content: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        doc="The message content text"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=func.now(),
        doc="Timestamp when the message was created"
    )
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('ix_messages_user_user_id', 'user_id'),
        Index('ix_messages_user_created_at', 'created_at'),
    )
    
    def __repr__(self) -> str:
        content_preview = self.content[:50] + "..." if len(self.content) > 50 else self.content
        return f"<MessageUser(id={self.id}, user_id={self.user_id}, role='{self.role}', content='{content_preview}')>"


class Memory(Base):
    """
    Memory model representing stored conversation memories with optional vector embeddings.
    
    Attributes:
        id: Unique identifier for the memory
        conversation_id: Foreign key reference to the conversation
        memory_type: Type of memory ("summary" | "episodic")
        text: The memory content text
        created_at: Timestamp when the memory was created
        embedding: Optional vector embedding for semantic search (if pgvector available)
    """
    __tablename__ = 'memories'
    
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4,
        doc="Unique identifier for the memory"
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey('conversations.id', ondelete='CASCADE'), 
        nullable=False,
        doc="Foreign key reference to the conversation"
    )
    memory_type: Mapped[str] = mapped_column(
        String(50), 
        nullable=False, 
        default="episodic",
        doc="Type of memory (summary|episodic)"
    )
    text: Mapped[str] = mapped_column(
        Text, 
        nullable=False,
        doc="The memory content text"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=func.now(),
        doc="Timestamp when the memory was created"
    )
    
    # Conditional embedding column based on pgvector availability
    if PGVECTOR_AVAILABLE and Vector:
        embedding: Mapped[Optional[List[float]]] = mapped_column(
            Vector(384), 
            nullable=True,
            doc="Vector embedding for semantic search (384 dimensions)"
        )
        
        # Create index for vector similarity search if pgvector is available
        __table_args__ = (
            Index('ix_memories_embedding', 'embedding', postgresql_using='ivfflat', postgresql_with={'lists': 100}),
            Index('ix_memories_conversation_type', 'conversation_id', 'memory_type'),
        )
    else:
        # Fallback for systems without pgvector - store as JSON
        embedding: Mapped[Optional[List[float]]] = mapped_column(
            JSON,
            nullable=True,
            doc="Vector embedding stored as JSON (fallback without pgvector)"
        )
        
        __table_args__ = (
            Index('ix_memories_conversation_type', 'conversation_id', 'memory_type'),
        )
    
    # Relationships
    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="memories")
    
    def __repr__(self) -> str:
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"<Memory(id={self.id}, type='{self.memory_type}', text='{text_preview}')>"


# Export the availability flag for use by repositories
__all__ = [
    'Base',
    'User', 
    'Persona',
    'Conversation',
    'MessageLog',
    'MessageUser',
    'Memory',
    'PGVECTOR_AVAILABLE'
]