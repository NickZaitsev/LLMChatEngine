"""
Async repository implementations for PostgreSQL storage.

This module implements the repository interfaces defined in storage.interfaces
using SQLAlchemy 2.x async ORM with PostgreSQL backend.
"""

import json
import logging
import math
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from uuid import UUID, uuid4
from pathlib import Path

from sqlalchemy import select, func, desc, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError, NoResultFound

from .interfaces import (
    Message, Memory, Conversation, User, Persona,
    MessageRepo, MemoryRepo, ConversationRepo, UserRepo, PersonaRepo
)
from .models import (
    Message as MessageModel,
    Memory as MemoryModel, 
    Conversation as ConversationModel,
    User as UserModel,
    Persona as PersonaModel,
    PGVECTOR_AVAILABLE
)

# Try to import tiktoken for accurate token counting
try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
    _encoding = tiktoken.get_encoding("cl100k_base")  # GPT-3.5/GPT-4 encoding
except ImportError:
    TIKTOKEN_AVAILABLE = False
    _encoding = None

logger = logging.getLogger(__name__)


class TokenEstimator:
    """Helper class for estimating token counts"""
    
    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count for given text.
        
        Uses tiktoken if available, otherwise falls back to character-based heuristic.
        
        Args:
            text: The text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        if not text:
            return 0
            
        if TIKTOKEN_AVAILABLE and _encoding:
            try:
                return len(_encoding.encode(text))
            except Exception as e:
                logger.warning(f"Failed to use tiktoken for token estimation: {e}")
                # Fall through to heuristic
        
        # Heuristic: ~4 characters per token for mixed content
        return max(1, len(text) // 4)


class PostgresMessageRepo:
    """PostgreSQL implementation of MessageRepo interface"""
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        Initialize the message repository.
        
        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker
        self.token_estimator = TokenEstimator()
    
    async def append_message(
        self, 
        conversation_id: str, 
        role: str, 
        content: str, 
        extra_data: Dict[str, Any] = None,
        token_count: int = 0
    ) -> Message:
        """
        Append a new message to a conversation.
        
        Args:
            conversation_id: UUID string of the conversation
            role: Role of the message sender ("user" | "assistant" | "system")
            content: The message content
            extra_data: Optional extra_data dictionary
            token_count: Pre-calculated token count (will estimate if 0)
            
        Returns:
            The created Message object
            
        Raises:
            ValueError: If conversation_id is invalid
            IntegrityError: If conversation doesn't exist
        """
        if extra_data is None:
            extra_data = {}
            
        if token_count == 0:
            token_count = self.estimate_tokens(content)
        
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            try:
                message_model = MessageModel(
                    conversation_id=conversation_uuid,
                    role=role,
                    content=content,
                    extra_data=extra_data,
                    token_count=token_count
                )
                
                session.add(message_model)
                await session.commit()
                await session.refresh(message_model)
                
                return Message(
                    id=message_model.id,
                    conversation_id=message_model.conversation_id,
                    role=message_model.role,
                    content=message_model.content,
                    extra_data=message_model.extra_data,
                    token_count=message_model.token_count,
                    created_at=message_model.created_at
                )
                
            except IntegrityError as e:
                await session.rollback()
                raise IntegrityError(f"Failed to create message: {e}") from e
    
    async def fetch_recent_messages(self, conversation_id: str, token_budget: int) -> List[Message]:
        """
        Fetch recent messages within a token budget.
        
        Args:
            conversation_id: UUID string of the conversation
            token_budget: Maximum tokens to include in response
            
        Returns:
            List of Message objects ordered by creation time (oldest first)
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            # Get messages ordered by created_at DESC for efficient trimming
            stmt = select(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            ).order_by(desc(MessageModel.created_at))
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            # Trim to token budget (keeping most recent messages)
            selected_messages = []
            current_tokens = 0
            
            for message in messages:
                if current_tokens + message.token_count <= token_budget:
                    selected_messages.append(message)
                    current_tokens += message.token_count
                else:
                    break
            
            # Reverse to return chronological order (oldest first)
            selected_messages.reverse()
            
            return [
                Message(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content,
                    extra_data=msg.extra_data,
                    token_count=msg.token_count,
                    created_at=msg.created_at
                )
                for msg in selected_messages
            ]
    
    async def fetch_messages_since(self, conversation_id: str, since_ts: datetime) -> List[Message]:
        """
        Fetch messages created after a specific timestamp.
        
        Args:
            conversation_id: UUID string of the conversation
            since_ts: Timestamp to filter messages after
            
        Returns:
            List of Message objects ordered by creation time
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(MessageModel).where(
                and_(
                    MessageModel.conversation_id == conversation_uuid,
                    MessageModel.created_at > since_ts
                )
            ).order_by(MessageModel.created_at)
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            return [
                Message(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content,
                    extra_data=msg.extra_data,
                    token_count=msg.token_count,
                    created_at=msg.created_at
                )
                for msg in messages
            ]
    
    async def list_messages(
        self, 
        conversation_id: str, 
        limit: int = 100, 
        offset: int = 0
    ) -> List[Message]:
        """
        List messages for a conversation with pagination.
        
        Args:
            conversation_id: UUID string of the conversation
            limit: Maximum number of messages to return
            offset: Number of messages to skip
            
        Returns:
            List of Message objects ordered by creation time
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            ).order_by(MessageModel.created_at).offset(offset).limit(limit)
            
            result = await session.execute(stmt)
            messages = result.scalars().all()
            
            return [
                Message(
                    id=msg.id,
                    conversation_id=msg.conversation_id,
                    role=msg.role,
                    content=msg.content,
                    extra_data=msg.extra_data,
                    token_count=msg.token_count,
                    created_at=msg.created_at
                )
                for msg in messages
            ]
    
    async def delete_messages(self, conversation_id: str) -> int:
        """
        Delete all messages for a conversation.
        
        Args:
            conversation_id: UUID string of the conversation
            
        Returns:
            Number of messages deleted
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            # Use bulk delete for efficiency
            from sqlalchemy import delete
            stmt = delete(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            )
            
            result = await session.execute(stmt)
            await session.commit()
            
            deleted_count = result.rowcount
            logger.info("Deleted %d messages for conversation %s", deleted_count, conversation_id)
            return deleted_count

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for given text.
        
        Args:
            text: The text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        return self.token_estimator.estimate_tokens(text)


class PostgresMemoryRepo:
    """PostgreSQL implementation of MemoryRepo interface with optional pgvector support"""
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession], use_pgvector: bool = True):
        """
        Initialize the memory repository.
        
        Args:
            session_maker: SQLAlchemy async session maker
            use_pgvector: Whether to use pgvector for similarity search
        """
        self.session_maker = session_maker
        self.use_pgvector = use_pgvector and PGVECTOR_AVAILABLE
        self.fallback_file = Path("memories_embeddings.json")
        
        if not self.use_pgvector:
            logger.info("pgvector not available, using file-based embedding storage")
    
    async def store_memory(
        self, 
        conversation_id: str, 
        text: str, 
        embedding: List[float], 
        memory_type: str = "episodic"
    ) -> Memory:
        """
        Store a memory with optional vector embedding.
        
        Args:
            conversation_id: UUID string of the conversation
            text: The memory text content
            embedding: Vector embedding of the text
            memory_type: Type of memory ("episodic" | "summary")
            
        Returns:
            The created Memory object
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            try:
                memory_model = MemoryModel(
                    conversation_id=conversation_uuid,
                    memory_type=memory_type,
                    text=text,
                    embedding=embedding
                )
                
                session.add(memory_model)
                await session.commit()
                await session.refresh(memory_model)
                
                # Store embedding in file if not using pgvector
                if not self.use_pgvector:
                    await self._store_embedding_to_file(str(memory_model.id), embedding)
                
                return Memory(
                    id=memory_model.id,
                    conversation_id=memory_model.conversation_id,
                    memory_type=memory_model.memory_type,
                    text=memory_model.text,
                    created_at=memory_model.created_at,
                    embedding=embedding
                )
                
            except IntegrityError as e:
                await session.rollback()
                raise IntegrityError(f"Failed to create memory: {e}") from e
    
    async def search_memories(
        self, 
        query_embedding: List[float], 
        top_k: int = 10, 
        similarity_threshold: float = 0.7
    ) -> List[Memory]:
        """
        Search for memories using vector similarity.
        
        Args:
            query_embedding: Query vector for similarity search
            top_k: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of Memory objects ordered by similarity (highest first)
        """
        async with self.session_maker() as session:
            if self.use_pgvector:
                # Use pgvector for efficient similarity search
                stmt = select(MemoryModel).order_by(
                    MemoryModel.embedding.cosine_distance(query_embedding)
                ).limit(top_k)
                
                result = await session.execute(stmt)
                memories = result.scalars().all()
                
                # Filter by similarity threshold
                filtered_memories = []
                for memory in memories:
                    if memory.embedding is not None and len(memory.embedding) > 0:
                        similarity = self._cosine_similarity(query_embedding, memory.embedding)
                        if similarity >= similarity_threshold:
                            filtered_memories.append((memory, similarity))
                
                # Sort by similarity descending
                filtered_memories.sort(key=lambda x: x[1], reverse=True)
                memories = [mem for mem, _ in filtered_memories]
                
            else:
                # Fallback: load all memories and compute similarity in Python
                stmt = select(MemoryModel)
                result = await session.execute(stmt)
                all_memories = result.scalars().all()
                
                memory_similarities = []
                for memory in all_memories:
                    if memory.embedding is not None and len(memory.embedding) > 0:
                        similarity = self._cosine_similarity(query_embedding, memory.embedding)
                        if similarity >= similarity_threshold:
                            memory_similarities.append((memory, similarity))
                
                # Sort by similarity descending and take top_k
                memory_similarities.sort(key=lambda x: x[1], reverse=True)
                memories = [mem for mem, _ in memory_similarities[:top_k]]
            
            return [
                Memory(
                    id=mem.id,
                    conversation_id=mem.conversation_id,
                    memory_type=mem.memory_type,
                    text=mem.text,
                    created_at=mem.created_at,
                    embedding=mem.embedding
                )
                for mem in memories
            ]
    
    async def list_memories(
        self, 
        conversation_id: str, 
        memory_type: Optional[str] = None
    ) -> List[Memory]:
        """
        List memories for a conversation, optionally filtered by type.
        
        Args:
            conversation_id: UUID string of the conversation
            memory_type: Optional memory type filter
            
        Returns:
            List of Memory objects ordered by creation time
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            conditions = [MemoryModel.conversation_id == conversation_uuid]
            if memory_type:
                conditions.append(MemoryModel.memory_type == memory_type)
            
            stmt = select(MemoryModel).where(
                and_(*conditions)
            ).order_by(MemoryModel.created_at)
            
            result = await session.execute(stmt)
            memories = result.scalars().all()
            
            return [
                Memory(
                    id=mem.id,
                    conversation_id=mem.conversation_id,
                    memory_type=mem.memory_type,
                    text=mem.text,
                    created_at=mem.created_at,
                    embedding=mem.embedding
                )
                for mem in memories
            ]
    
    async def _store_embedding_to_file(self, memory_id: str, embedding: List[float]):
        """Store embedding to file when pgvector is not available"""
        try:
            # Load existing embeddings
            embeddings = {}
            if self.fallback_file.exists():
                with open(self.fallback_file, 'r') as f:
                    embeddings = json.load(f)
            
            # Add new embedding
            embeddings[memory_id] = embedding
            
            # Save back to file
            with open(self.fallback_file, 'w') as f:
                json.dump(embeddings, f)
                
        except Exception as e:
            logger.error(f"Failed to store embedding to file: {e}")
    
    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        try:
            dot_product = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
                
            return dot_product / (norm_a * norm_b)
        except (ValueError, ZeroDivisionError):
            return 0.0


class PostgresConversationRepo:
    """PostgreSQL implementation of ConversationRepo interface"""
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        Initialize the conversation repository.
        
        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker
    
    async def create_conversation(
        self, 
        user_id: str, 
        persona_id: str, 
        title: str = None, 
        extra_data: Dict[str, Any] = None
    ) -> Conversation:
        """
        Create a new conversation.
        
        Args:
            user_id: UUID string of the user
            persona_id: UUID string of the persona
            title: Optional conversation title
            extra_data: Optional extra_data dictionary
            
        Returns:
            The created Conversation object
        """
        if extra_data is None:
            extra_data = {}
        
        try:
            user_uuid = UUID(user_id)
            persona_uuid = UUID(persona_id)
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {e}") from e
        
        async with self.session_maker() as session:
            try:
                conversation_model = ConversationModel(
                    user_id=user_uuid,
                    persona_id=persona_uuid,
                    title=title,
                    extra_data=extra_data
                )
                
                session.add(conversation_model)
                await session.commit()
                await session.refresh(conversation_model)
                
                return Conversation(
                    id=conversation_model.id,
                    user_id=conversation_model.user_id,
                    persona_id=conversation_model.persona_id,
                    title=conversation_model.title,
                    extra_data=conversation_model.extra_data,
                    created_at=conversation_model.created_at
                )
                
            except IntegrityError as e:
                await session.rollback()
                raise IntegrityError(f"Failed to create conversation: {e}") from e
    
    async def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """
        Get a conversation by ID.
        
        Args:
            conversation_id: UUID string of the conversation
            
        Returns:
            Conversation object if found, None otherwise
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(ConversationModel).where(
                ConversationModel.id == conversation_uuid
            )
            
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
                
            return Conversation(
                id=conversation.id,
                user_id=conversation.user_id,
                persona_id=conversation.persona_id,
                title=conversation.title,
                extra_data=conversation.extra_data,
                created_at=conversation.created_at
            )
    
    async def list_conversations(self, user_id: str) -> List[Conversation]:
        """
        List all conversations for a user.
        
        Args:
            user_id: UUID string of the user
            
        Returns:
            List of Conversation objects ordered by creation time (newest first)
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise ValueError(f"Invalid user_id format: {user_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(ConversationModel).where(
                ConversationModel.user_id == user_uuid
            ).order_by(desc(ConversationModel.created_at))
            
            result = await session.execute(stmt)
            conversations = result.scalars().all()
            
            return [
                Conversation(
                    id=conv.id,
                    user_id=conv.user_id,
                    persona_id=conv.persona_id,
                    title=conv.title,
                    extra_data=conv.extra_data,
                    created_at=conv.created_at
                )
                for conv in conversations
            ]
    
    async def update_conversation(
        self, 
        conversation_id: str, 
        title: str = None, 
        extra_data: Dict[str, Any] = None
    ) -> Optional[Conversation]:
        """
        Update an existing conversation.
        
        Args:
            conversation_id: UUID string of the conversation
            title: New title (if provided)
            extra_data: New extra_data (if provided)
            
        Returns:
            Updated Conversation object if found, None otherwise
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(ConversationModel).where(
                ConversationModel.id == conversation_uuid
            )
            
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()
            
            if not conversation:
                return None
            
            # Update fields if provided
            if title is not None:
                conversation.title = title
            if extra_data is not None:
                conversation.extra_data = extra_data
            
            await session.commit()
            await session.refresh(conversation)
            
            return Conversation(
                id=conversation.id,
                user_id=conversation.user_id,
                persona_id=conversation.persona_id,
                title=conversation.title,
                extra_data=conversation.extra_data,
                created_at=conversation.created_at
            )


class PostgresUserRepo:
    """PostgreSQL implementation of UserRepo interface"""
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        Initialize the user repository.
        
        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker
    
    async def create_user(self, username: str, extra_data: Dict[str, Any] = None) -> User:
        """
        Create a new user.
        
        Args:
            username: Unique username
            extra_data: Optional extra_data dictionary
            
        Returns:
            The created User object
            
        Raises:
            IntegrityError: If username already exists
        """
        if extra_data is None:
            extra_data = {}
        
        async with self.session_maker() as session:
            try:
                user_model = UserModel(
                    username=username,
                    extra_data=extra_data
                )
                
                session.add(user_model)
                await session.commit()
                await session.refresh(user_model)
                
                return User(
                    id=user_model.id,
                    username=user_model.username,
                    extra_data=user_model.extra_data
                )
                
            except IntegrityError as e:
                await session.rollback()
                raise IntegrityError(f"Username '{username}' already exists") from e
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """
        Get a user by ID.
        
        Args:
            user_id: UUID string of the user
            
        Returns:
            User object if found, None otherwise
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise ValueError(f"Invalid user_id format: {user_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(UserModel).where(UserModel.id == user_uuid)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
                
            return User(
                id=user.id,
                username=user.username,
                extra_data=user.extra_data
            )
    
    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get a user by username.
        
        Args:
            username: The username to search for
            
        Returns:
            User object if found, None otherwise
        """
        async with self.session_maker() as session:
            stmt = select(UserModel).where(UserModel.username == username)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return None
                
            return User(
                id=user.id,
                username=user.username,
                extra_data=user.extra_data
            )


class PostgresPersonaRepo:
    """PostgreSQL implementation of PersonaRepo interface"""
    
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        Initialize the persona repository.
        
        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker
    
    async def create_persona(
        self, 
        user_id: str, 
        name: str, 
        config: Dict[str, Any] = None
    ) -> Persona:
        """
        Create a new persona.
        
        Args:
            user_id: UUID string of the owning user
            name: Display name of the persona
            config: Optional configuration dictionary
            
        Returns:
            The created Persona object
        """
        if config is None:
            config = {}
        
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise ValueError(f"Invalid user_id format: {user_id}") from e
        
        async with self.session_maker() as session:
            try:
                persona_model = PersonaModel(
                    user_id=user_uuid,
                    name=name,
                    config=config
                )
                
                session.add(persona_model)
                await session.commit()
                await session.refresh(persona_model)
                
                return Persona(
                    id=persona_model.id,
                    user_id=persona_model.user_id,
                    name=persona_model.name,
                    config=persona_model.config
                )
                
            except IntegrityError as e:
                await session.rollback()
                raise IntegrityError(f"Failed to create persona: {e}") from e
    
    async def get_persona(self, persona_id: str) -> Optional[Persona]:
        """
        Get a persona by ID.
        
        Args:
            persona_id: UUID string of the persona
            
        Returns:
            Persona object if found, None otherwise
        """
        try:
            persona_uuid = UUID(persona_id)
        except ValueError as e:
            raise ValueError(f"Invalid persona_id format: {persona_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(PersonaModel).where(PersonaModel.id == persona_uuid)
            result = await session.execute(stmt)
            persona = result.scalar_one_or_none()
            
            if not persona:
                return None
                
            return Persona(
                id=persona.id,
                user_id=persona.user_id,
                name=persona.name,
                config=persona.config
            )
    
    async def list_personas(self, user_id: str) -> List[Persona]:
        """
        List all personas for a user.
        
        Args:
            user_id: UUID string of the user
            
        Returns:
            List of Persona objects
        """
        try:
            user_uuid = UUID(user_id)
        except ValueError as e:
            raise ValueError(f"Invalid user_id format: {user_id}") from e
        
        async with self.session_maker() as session:
            stmt = select(PersonaModel).where(PersonaModel.user_id == user_uuid)
            result = await session.execute(stmt)
            personas = result.scalars().all()
            
            return [
                Persona(
                    id=persona.id,
                    user_id=persona.user_id,
                    name=persona.name,
                    config=persona.config
                )
                for persona in personas
            ]


# Export all repository implementations
__all__ = [
    'TokenEstimator',
    'PostgresMessageRepo',
    'PostgresMemoryRepo', 
    'PostgresConversationRepo',
    'PostgresUserRepo',
    'PostgresPersonaRepo',
    'TIKTOKEN_AVAILABLE',
    'PGVECTOR_AVAILABLE'
]