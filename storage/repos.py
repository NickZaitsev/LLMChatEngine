"""
Async repository implementations for PostgreSQL storage.

This module implements the repository interfaces defined in storage.interfaces
using SQLAlchemy 2.x async ORM with PostgreSQL backend.
"""

import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from uuid import UUID, uuid4

from core.tokens import TokenCounter
from sqlalchemy import select, func, desc, and_, or_, text, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.exc import IntegrityError, NoResultFound

from .interfaces import (
    Message, Conversation, User, Persona, MessageLog, MessageUser,
    MessageRepo, ConversationRepo, UserRepo, PersonaRepo, MessageHistoryRepo,
    UserBotSettings
)
from .models import (
    Message as MessageModel,
    Conversation as ConversationModel,
    User as UserModel,
    Persona as PersonaModel,
    UserBotSettings as UserBotSettingsModel,
    MessageLog as MessageLogModel,
    MessageUser as MessageUserModel,
)

logger = logging.getLogger(__name__)


class TokenEstimator(TokenCounter):
    """Compatibility wrapper around the shared token counter."""


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
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    extra_data=m.extra_data,
                    token_count=m.token_count,
                    created_at=m.created_at
                )
                for m in selected_messages
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
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    extra_data=m.extra_data,
                    token_count=m.token_count,
                    created_at=m.created_at
                )
                for m in messages
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
            stmt = delete(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            )

            result = await session.execute(stmt)
            await session.commit()

            deleted_count = result.rowcount
            # Reduced logging - let the caller handle detailed logging
            # logger.info("Deleted %d messages for conversation %s", deleted_count, conversation_id)
            return deleted_count

    async def get_last_user_message(self, conversation_id: str) -> Optional[Message]:
        """
        Get the last user message for a conversation.

        Args:
            conversation_id: UUID string of the conversation

        Returns:
            The last user Message object if found, None otherwise
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e

        async with self.session_maker() as session:
            stmt = select(MessageModel).where(
                and_(
                    MessageModel.conversation_id == conversation_uuid,
                    MessageModel.role == 'user'
                )
            ).order_by(desc(MessageModel.created_at)).limit(1)

            result = await session.execute(stmt)
            message = result.scalar_one_or_none()

            if not message:
                return None

            return Message(
                id=message.id,
                conversation_id=message.conversation_id,
                role=message.role,
                content=message.content,
                extra_data=message.extra_data,
                token_count=message.token_count,
                created_at=message.created_at
            )

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for given text.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        return self.token_estimator.estimate_tokens(text)

    async def count_active_messages(self, conversation_id: str, last_summarized_message_id: Optional[UUID]) -> int:
        """
        Count active (unsummarized) messages in a conversation.
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e

        async with self.session_maker() as session:
            stmt = select(func.count(MessageModel.id)).where(
                MessageModel.conversation_id == conversation_uuid
            )
            if last_summarized_message_id:
                # We need to get the created_at timestamp of the last summarized message
                last_summarized_message = await session.get(MessageModel, last_summarized_message_id)
                if last_summarized_message:
                    stmt = stmt.where(MessageModel.created_at > last_summarized_message.created_at)

            result = await session.execute(stmt)
            return result.scalar_one()

    async def fetch_active_messages(self, conversation_id: str, token_budget: int, last_summarized_message_id: Optional[UUID]) -> List[Message]:
        """
        Fetch recent active (unsummarized) messages within a token budget.
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e

        async with self.session_maker() as session:
            stmt = select(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            )
            if last_summarized_message_id:
                last_summarized_message = await session.get(MessageModel, last_summarized_message_id)
                if last_summarized_message:
                    stmt = stmt.where(MessageModel.created_at > last_summarized_message.created_at)

            stmt = stmt.order_by(desc(MessageModel.created_at))

            result = await session.execute(stmt)
            messages = result.scalars().all()

            selected_messages = []
            current_tokens = 0
            for message in messages:
                if current_tokens + message.token_count <= token_budget:
                    selected_messages.append(message)
                    current_tokens += message.token_count
                else:
                    break

            selected_messages.reverse()

            return [
                Message(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    extra_data=m.extra_data,
                    token_count=m.token_count,
                    created_at=m.created_at
                ) for m in selected_messages
            ]

    async def get_messages_for_summary(self, conversation_id: str, last_summarized_message_id: Optional[UUID]) -> List[Message]:
        """
        Fetch all active messages to be summarized.
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e

        async with self.session_maker() as session:
            stmt = select(MessageModel).where(
                MessageModel.conversation_id == conversation_uuid
            )
            if last_summarized_message_id:
                last_summarized_message = await session.get(MessageModel, last_summarized_message_id)
                if last_summarized_message:
                    stmt = stmt.where(MessageModel.created_at > last_summarized_message.created_at)

            stmt = stmt.order_by(MessageModel.created_at.asc())
            result = await session.execute(stmt)
            messages = result.scalars().all()

            return [
                Message(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    extra_data=m.extra_data,
                    token_count=m.token_count,
                    created_at=m.created_at
                ) for m in messages
            ]


class PostgresMessageHistoryRepo:
    """PostgreSQL implementation of MessageHistoryRepo interface"""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        """
        Initialize the message history repository.

        Args:
            session_maker: SQLAlchemy async session maker
        """
        self.session_maker = session_maker

    async def save_message(self, user_id: UUID, role: str, content: str, bot_id: Optional[UUID] = None) -> tuple[MessageLog, MessageUser]:
        """
        Save a message to both messages_log and messages_user tables.

        Args:
            user_id: Telegram user ID (as UUID)
            role: Role of the message sender ("user" | "bot")
            content: The message content

        Returns:
            Tuple of (MessageLog, MessageUser) objects
        """
        async with self.session_maker() as session:
            try:
                # Create message log entry (permanent)
                message_log_model = MessageLogModel(
                    user_id=user_id,
                    role=role,
                    content=content,
                    bot_id=bot_id,
                )

                # Create user message entry (can be cleared)
                message_user_model = MessageUserModel(
                    user_id=user_id,
                    role=role,
                    content=content,
                    bot_id=bot_id,
                )

                session.add(message_log_model)
                session.add(message_user_model)
                await session.commit()
                await session.refresh(message_log_model)
                await session.refresh(message_user_model)

                message_log = MessageLog(
                    id=message_log_model.id,
                    user_id=message_log_model.user_id,
                    role=message_log_model.role,
                    content=message_log_model.content,
                    created_at=message_log_model.created_at,
                    bot_id=message_log_model.bot_id,
                )

                message_user = MessageUser(
                    id=message_user_model.id,
                    user_id=message_user_model.user_id,
                    role=message_user_model.role,
                    content=message_user_model.content,
                    created_at=message_user_model.created_at,
                    bot_id=message_user_model.bot_id,
                )

                # Reduced logging - let the caller handle detailed logging
                # logger.info("Saved message to both tables: user_id=%s, role=%s, length=%d chars",
                #            user_id, role, len(content))

                return (message_log, message_user)

            except Exception as e:
                await session.rollback()
                logger.error("Failed to save message to history tables: %s", e)
                raise

    async def get_user_history(self, user_id: UUID, limit: int = 100, bot_id: Optional[UUID] = None) -> List[MessageUser]:
        """
        Get user message history from messages_user table.

        Args:
            user_id: Telegram user ID (as UUID)
            limit: Maximum number of messages to return

        Returns:
            List of MessageUser objects ordered by creation time
        """
        async with self.session_maker() as session:
            try:
                stmt = select(MessageUserModel).where(
                    MessageUserModel.user_id == user_id
                )
                if bot_id is not None:
                    stmt = stmt.where(MessageUserModel.bot_id == bot_id)
                stmt = stmt.order_by(MessageUserModel.created_at).limit(limit)

                result = await session.execute(stmt)
                messages = result.scalars().all()

                return [
                    MessageUser(
                        id=msg.id,
                        user_id=msg.user_id,
                        role=msg.role,
                        content=msg.content,
                        created_at=msg.created_at,
                        bot_id=msg.bot_id,
                    )
                    for msg in messages
                ]

            except Exception as e:
                logger.error("Failed to get user history: %s", e)
                return []

    async def clear_user_history(self, user_id: UUID, bot_id: Optional[UUID] = None) -> int:
        """
        Clear user message history from messages_user table only.

        Args:
            user_id: Telegram user ID (as UUID)

        Returns:
            Number of messages deleted
        """
        async with self.session_maker() as session:
            try:
                stmt = delete(MessageUserModel).where(
                    MessageUserModel.user_id == user_id
                )
                if bot_id is not None:
                    stmt = stmt.where(MessageUserModel.bot_id == bot_id)

                result = await session.execute(stmt)
                await session.commit()

                deleted_count = result.rowcount
                # Reduced logging - let the caller handle detailed logging
                # logger.info("Cleared %d messages from messages_user table for user %s", deleted_count, user_id)
                return deleted_count

            except Exception as e:
                await session.rollback()
                logger.error("Failed to clear user history: %s", e)
                return 0


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
        bot_id: Optional[str] = None,
        title: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None
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
            bot_uuid = UUID(bot_id) if bot_id else None
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {e}") from e

        async with self.session_maker() as session:
            try:
                conversation_model = ConversationModel(
                    user_id=user_uuid,
                    persona_id=persona_uuid,
                    bot_id=bot_uuid,
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
                    bot_id=conversation_model.bot_id,
                    title=conversation_model.title,
                    extra_data=conversation_model.extra_data,
                    created_at=conversation_model.created_at,
                    summary=conversation_model.summary,
                    last_summarized_message_id=conversation_model.last_summarized_message_id,
                    last_memorized_message_id=getattr(conversation_model, 'last_memorized_message_id', None)
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
                bot_id=conversation.bot_id,
                title=conversation.title,
                extra_data=conversation.extra_data,
                created_at=conversation.created_at,
                summary=conversation.summary,
                last_summarized_message_id=conversation.last_summarized_message_id,
                last_memorized_message_id=getattr(conversation, 'last_memorized_message_id', None)
            )

    async def list_conversations(self, user_id: str, bot_id: Optional[str] = None) -> List[Conversation]:
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
            conditions = [ConversationModel.user_id == user_uuid]
            if bot_id:
                try:
                    bot_uuid = UUID(bot_id)
                    conditions.append(ConversationModel.bot_id == bot_uuid)
                except ValueError:
                    logger.warning(f"Invalid bot_id format in list_conversations: {bot_id}")

            stmt = select(ConversationModel).where(
                and_(*conditions)
            ).order_by(desc(ConversationModel.created_at))

            result = await session.execute(stmt)
            conversations = result.scalars().all()

            return [
                Conversation(
                    id=conv.id,
                    user_id=conv.user_id,
                    persona_id=conv.persona_id,
                    bot_id=conv.bot_id,
                    title=conv.title,
                    extra_data=conv.extra_data,
                    created_at=conv.created_at,
                    summary=conv.summary,
                    last_summarized_message_id=conv.last_summarized_message_id,
                    last_memorized_message_id=getattr(conv, 'last_memorized_message_id', None)
                )
                for conv in conversations
            ]

    async def update_conversation(
        self,
        conversation_id: str,
        title: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
        last_summarized_message_id: Optional[UUID] = None,
        last_memorized_message_id: Optional[UUID] = None
    ) -> Optional[Conversation]:
        """
        Update an existing conversation.
        """
        try:
            conversation_uuid = UUID(conversation_id)
        except ValueError as e:
            raise ValueError(f"Invalid conversation_id format: {conversation_id}") from e

        async with self.session_maker() as session:
            stmt = select(ConversationModel).where(ConversationModel.id == conversation_uuid)
            result = await session.execute(stmt)
            conversation = result.scalar_one_or_none()

            if not conversation:
                return None

            if title is not None:
                conversation.title = title
            if extra_data is not None:
                conversation.extra_data = extra_data
            if summary is not None:
                conversation.summary = summary
            if last_summarized_message_id is not None:
                conversation.last_summarized_message_id = last_summarized_message_id
            if last_memorized_message_id is not None:
                conversation.last_memorized_message_id = last_memorized_message_id

            await session.commit()
            await session.refresh(conversation)

            return Conversation(
                id=conversation.id,
                user_id=conversation.user_id,
                persona_id=conversation.persona_id,
                bot_id=conversation.bot_id,
                title=conversation.title,
                extra_data=conversation.extra_data,
                created_at=conversation.created_at,
                summary=conversation.summary,
                last_summarized_message_id=conversation.last_summarized_message_id,
                last_memorized_message_id=getattr(conversation, 'last_memorized_message_id', None)
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
        if not username:
            return None

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


class PostgresUserBotSettingsRepo:
    """PostgreSQL implementation of UserBotSettingsRepo interface."""

    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self.session_maker = session_maker

    async def get_or_create_settings(self, user_id: str, bot_id: str) -> UserBotSettings:
        """Fetch user bot settings or create an empty settings record."""
        settings = await self.get_settings(user_id, bot_id)
        if settings:
            return settings

        try:
            user_uuid = UUID(user_id)
            bot_uuid = UUID(bot_id)
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {e}") from e

        async with self.session_maker() as session:
            model = UserBotSettingsModel(
                user_id=user_uuid,
                bot_id=bot_uuid,
                settings={},
            )
            session.add(model)
            await session.commit()
            await session.refresh(model)
            return UserBotSettings(
                id=model.id,
                user_id=model.user_id,
                bot_id=model.bot_id,
                settings=model.settings,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )

    async def get_settings(self, user_id: str, bot_id: str) -> Optional[UserBotSettings]:
        """Fetch settings for a user and bot pair."""
        try:
            user_uuid = UUID(user_id)
            bot_uuid = UUID(bot_id)
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {e}") from e

        async with self.session_maker() as session:
            stmt = select(UserBotSettingsModel).where(
                and_(
                    UserBotSettingsModel.user_id == user_uuid,
                    UserBotSettingsModel.bot_id == bot_uuid,
                )
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            if not model:
                return None

            return UserBotSettings(
                id=model.id,
                user_id=model.user_id,
                bot_id=model.bot_id,
                settings=model.settings,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )

    async def update_settings(self, user_id: str, bot_id: str, settings: Dict[str, Any]) -> UserBotSettings:
        """Merge and persist settings for a user and bot pair."""
        try:
            user_uuid = UUID(user_id)
            bot_uuid = UUID(bot_id)
        except ValueError as e:
            raise ValueError(f"Invalid UUID format: {e}") from e

        async with self.session_maker() as session:
            stmt = select(UserBotSettingsModel).where(
                and_(
                    UserBotSettingsModel.user_id == user_uuid,
                    UserBotSettingsModel.bot_id == bot_uuid,
                )
            )
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()

            if not model:
                model = UserBotSettingsModel(
                    user_id=user_uuid,
                    bot_id=bot_uuid,
                    settings=dict(settings or {}),
                )
                session.add(model)
            else:
                merged_settings = dict(model.settings or {})
                merged_settings.update(settings or {})
                model.settings = merged_settings

            await session.commit()
            await session.refresh(model)

            return UserBotSettings(
                id=model.id,
                user_id=model.user_id,
                bot_id=model.bot_id,
                settings=model.settings,
                created_at=model.created_at,
                updated_at=model.updated_at,
            )


# Export all repository implementations
__all__ = [
    'TokenEstimator',
    'PostgresMessageRepo',
    'PostgresMessageHistoryRepo',
    'PostgresConversationRepo',
    'PostgresUserRepo',
    'PostgresPersonaRepo',
    'PostgresUserBotSettingsRepo',
]
