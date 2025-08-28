"""
Storage factory module for the AI girlfriend bot.

This module provides a factory function to create storage instances with 
PostgreSQL-backed repositories. It handles database connection setup,
session management, and repository initialization.
"""

import logging
from typing import Optional
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy import text

from .models import Base, PGVECTOR_AVAILABLE
from .repos import (
    PostgresMessageRepo,
    PostgresMessageHistoryRepo,
    PostgresMemoryRepo, 
    PostgresConversationRepo,
    PostgresUserRepo,
    PostgresPersonaRepo
)

logger = logging.getLogger(__name__)


@dataclass
class Storage:
    """
    Storage container providing access to all repository instances.
    
    Attributes:
        messages: Message repository instance
        message_history: Message history repository instance
        memories: Memory repository instance  
        conversations: Conversation repository instance
        users: User repository instance
        personas: Persona repository instance
        engine: SQLAlchemy async engine
        session_maker: SQLAlchemy async session maker
        use_pgvector: Whether pgvector is being used for memory search
    """
    messages: PostgresMessageRepo
    message_history: PostgresMessageHistoryRepo
    memories: PostgresMemoryRepo
    conversations: PostgresConversationRepo
    users: PostgresUserRepo
    personas: PostgresPersonaRepo
    engine: AsyncEngine
    session_maker: async_sessionmaker
    use_pgvector: bool
    
    async def close(self):
        """Close the database connection pool"""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connection pool closed")
    
    async def health_check(self) -> bool:
        """
        Perform a basic health check on the database connection.
        
        Returns:
            True if the database is accessible, False otherwise
        """
        try:
            async with self.session_maker() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False
    
    def __repr__(self) -> str:
        return f"<Storage(pgvector={self.use_pgvector}, engine={self.engine})>"


async def create_storage(db_url: str, use_pgvector: bool = True) -> Storage:
    """
    Create a Storage instance with PostgreSQL-backed repositories.
    
    This factory function sets up the database connection, creates all necessary
    tables, and initializes repository instances with proper session management.
    
    Args:
        db_url: PostgreSQL database URL (e.g., "postgresql+asyncpg://user:pass@host/db")
        use_pgvector: Whether to use pgvector for memory embeddings (defaults to True)
        
    Returns:
        Storage instance with all repositories initialized
        
    Raises:
        ValueError: If db_url is invalid or database connection fails
        RuntimeError: If pgvector is requested but not available
        
    Examples:
        >>> storage = await create_storage(
        ...     "postgresql+asyncpg://user:pass@localhost/ai_bot",
        ...     use_pgvector=True
        ... )
        >>> message = await storage.messages.append_message(
        ...     conversation_id="...", 
        ...     role="user", 
        ...     content="Hello!"
        ... )
        >>> await storage.close()
    """
    if not db_url:
        raise ValueError("Database URL cannot be empty")
    
    if not db_url.startswith(('postgresql+asyncpg://', 'postgresql+psycopg://', 'sqlite+aiosqlite://')):
        logger.warning(f"Database URL should use async driver (asyncpg/psycopg/aiosqlite): {db_url}")
    
    # Check pgvector availability
    if use_pgvector and not PGVECTOR_AVAILABLE:
        logger.warning("pgvector requested but not available, falling back to file-based embeddings")
        use_pgvector = False
    
    logger.info(f"Creating storage with database: {_mask_db_url(db_url)}, pgvector: {use_pgvector}")
    
    try:
        # Create async engine with appropriate connection pooling
        engine_kwargs = {
            "echo": False,  # Set to True for SQL debugging
            "future": True,
        }
        
        if 'sqlite' in db_url:
            # SQLite doesn't support connection pooling the same way
            engine_kwargs["poolclass"] = NullPool
            logger.info("Using SQLite with NullPool")
        else:
            # PostgreSQL with connection pooling - don't specify poolclass for async engines
            engine_kwargs.update({
                "pool_size": 10,
                "max_overflow": 20,
                "pool_pre_ping": True,
                "pool_recycle": 3600,  # 1 hour
            })
            logger.info("Using PostgreSQL with connection pooling")
        
        engine = create_async_engine(db_url, **engine_kwargs)
        
        # Test the connection
        try:
            async with engine.begin() as conn:
                await conn.run_sync(lambda _: None)  # Simple connection test
            logger.info("Database connection test successful")
        except Exception as e:
            await engine.dispose()
            raise ValueError(f"Failed to connect to database: {e}") from e
        
        # Create async session maker
        session_maker = async_sessionmaker(
            engine, 
            expire_on_commit=False,
            autoflush=True,
            autocommit=False
        )
        
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema created/updated successfully")
        
        # Initialize repositories
        messages_repo = PostgresMessageRepo(session_maker)
        message_history_repo = PostgresMessageHistoryRepo(session_maker)
        memories_repo = PostgresMemoryRepo(session_maker, use_pgvector)
        conversations_repo = PostgresConversationRepo(session_maker)
        users_repo = PostgresUserRepo(session_maker)
        personas_repo = PostgresPersonaRepo(session_maker)
        
        storage = Storage(
            messages=messages_repo,
            message_history=message_history_repo,
            memories=memories_repo,
            conversations=conversations_repo,
            users=users_repo,
            personas=personas_repo,
            engine=engine,
            session_maker=session_maker,
            use_pgvector=use_pgvector
        )
        
        logger.info("Storage instance created successfully")
        return storage
        
    except Exception as e:
        logger.error(f"Failed to create storage: {e}")
        # Clean up engine if it was created
        if 'engine' in locals():
            try:
                await engine.dispose()
            except Exception:
                pass
        raise


def _mask_db_url(db_url: str) -> str:
    """
    Mask sensitive information in database URL for logging.
    
    Args:
        db_url: Full database URL
        
    Returns:
        Database URL with password masked
    """
    try:
        if '@' in db_url and '://' in db_url:
            scheme_and_auth, rest = db_url.split('://', 1)
            if '@' in rest:
                auth, host_and_path = rest.split('@', 1)
                if ':' in auth:
                    user, _ = auth.split(':', 1)
                    return f"{scheme_and_auth}://{user}:***@{host_and_path}"
        return db_url
    except Exception:
        return "***masked***"



# Import token estimator for backward compatibility
from .repos import TokenEstimator

# Export public API
__all__ = [
    'Storage',
    'create_storage', 
    'TokenEstimator',
    'PGVECTOR_AVAILABLE'
]

# Version information
__version__ = '1.0.0'