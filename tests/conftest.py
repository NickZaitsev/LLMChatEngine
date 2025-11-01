"""
Pytest configuration and fixtures for storage tests.

This module provides fixtures for testing the storage system using
an in-memory SQLite database for speed and isolation.
"""

import asyncio
import pytest
import pytest_asyncio
import uuid
from typing import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from storage.models import Base
from storage.repos import (
    PostgresMessageRepo, PostgresMessageHistoryRepo, PostgresMemoryRepo, PostgresConversationRepo,
    PostgresUserRepo, PostgresPersonaRepo
)
from storage import create_storage, Storage
from storage_conversation_manager import PostgresConversationManager
from app_context import AppContext


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """Create an async SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    await engine.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    """Create an async session maker."""
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False
    )


@pytest_asyncio.fixture
async def session(session_maker) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async with session_maker() as session:
        yield session


@pytest_asyncio.fixture
async def storage(engine) -> AsyncGenerator[Storage, None]:
    """Create a storage instance for testing using the shared engine."""
    # Use the shared engine instead of creating a separate database
    session_maker = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False
    )
    
    # Create storage using the shared engine components
    from storage.repos import (
        PostgresMessageRepo, PostgresMemoryRepo, PostgresConversationRepo,
        PostgresUserRepo, PostgresPersonaRepo
    )
    
    storage = Storage(
        messages=PostgresMessageRepo(session_maker),
        message_history=PostgresMessageHistoryRepo(session_maker),
        memories=PostgresMemoryRepo(session_maker, use_pgvector=False),
        conversations=PostgresConversationRepo(session_maker),
        users=PostgresUserRepo(session_maker),
        personas=PostgresPersonaRepo(session_maker),
        engine=engine,
        session_maker=session_maker,
        use_pgvector=False
    )
    
    yield storage
    # No need to close since we're sharing the engine


@pytest_asyncio.fixture
async def message_repo(session_maker) -> PostgresMessageRepo:
    """Create a message repository for testing."""
    return PostgresMessageRepo(session_maker)


@pytest_asyncio.fixture
async def memory_repo(session_maker) -> PostgresMemoryRepo:
    """Create a memory repository for testing."""
    return PostgresMemoryRepo(session_maker, use_pgvector=False)


@pytest_asyncio.fixture
async def conversation_repo(session_maker) -> PostgresConversationRepo:
    """Create a conversation repository for testing."""
    return PostgresConversationRepo(session_maker)


@pytest_asyncio.fixture
async def user_repo(session_maker) -> PostgresUserRepo:
    """Create a user repository for testing."""
    return PostgresUserRepo(session_maker)


@pytest_asyncio.fixture
async def persona_repo(session_maker) -> PostgresPersonaRepo:
    """Create a persona repository for testing."""
    return PostgresPersonaRepo(session_maker)


@pytest_asyncio.fixture
async def sample_user(user_repo: PostgresUserRepo):
    """Create a sample user for testing."""
    return await user_repo.create_user(
        username="test_user",
        extra_data={"test": True}
    )


@pytest_asyncio.fixture
async def sample_persona(persona_repo: PostgresPersonaRepo, sample_user):
    """Create a sample persona for testing."""
    return await persona_repo.create_persona(
        user_id=str(sample_user.id),
        name="Test Persona",
        config={"personality": "friendly"}
    )


@pytest_asyncio.fixture
async def sample_conversation(conversation_repo: PostgresConversationRepo, sample_user, sample_persona):
    """Create a sample conversation for testing."""
    return await conversation_repo.create_conversation(
        user_id=str(sample_user.id),
        persona_id=str(sample_persona.id),
        title="Test Conversation"
    )


@pytest.fixture
def sample_embedding():
    """Create a sample embedding vector for testing."""
    return [0.1] * 384  # 384-dimensional vector with all values 0.1


# Utility functions for tests
def generate_uuid() -> str:
    """Generate a UUID string for testing."""
    return str(uuid.uuid4())


def assert_uuid_string(value: str) -> None:
    """Assert that a string is a valid UUID."""
    uuid.UUID(value)  # Will raise ValueError if invalid

@pytest_asyncio.fixture
async def app_context(engine) -> "AppContext":
    """Create an application context for testing with an in-memory SQLite database."""
    from app_context import AppContext
    from ai_handler import AIHandler
    from config import MAX_ACTIVE_MESSAGES, SUMMARIZATION_PROMPT

    # Use the in-memory engine for the test session
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    class MockConfig:
        MAX_ACTIVE_MESSAGES = 10
        SUMMARIZATION_PROMPT = "Summarize: {text}"

    # Manually construct the AppContext with the in-memory database
    context = AppContext()
    context.conversation_manager = PostgresConversationManager(db_url=None, use_pgvector=False)
    context.conversation_manager.storage = Storage(
        messages=PostgresMessageRepo(session_maker),
        message_history=PostgresMessageHistoryRepo(session_maker),
        memories=PostgresMemoryRepo(session_maker, use_pgvector=False),
        conversations=PostgresConversationRepo(session_maker),
        users=PostgresUserRepo(session_maker),
        personas=PostgresPersonaRepo(session_maker),
        engine=engine,
        session_maker=session_maker,
        use_pgvector=False
    )
    context.ai_handler = AIHandler(prompt_assembler=None)
    context.config = MockConfig()
    
    return context