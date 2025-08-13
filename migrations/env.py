"""
Alembic environment configuration for async SQLAlchemy.

This file configures Alembic to work with async SQLAlchemy and PostgreSQL,
including optional pgvector support for vector embeddings.
"""

import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Import your models here
from storage.models import Base

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata


def get_database_url():
    """
    Get the database URL from environment variables or config.
    
    Priority:
    1. DATABASE_URL environment variable
    2. Constructed from individual environment variables
    3. Config file default (for development)
    """
    # Try environment variable first
    db_url = os.getenv('DATABASE_URL')
    if db_url:
        # Convert sync URL to async if needed
        if db_url.startswith('postgresql://'):
            db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        return db_url
    
    # Try constructing from individual environment variables
    db_host = os.getenv('DB_HOST', 'localhost')
    db_port = os.getenv('DB_PORT', '5432')
    db_name = os.getenv('DB_NAME', 'ai_bot_db')
    db_user = os.getenv('DB_USER', 'ai_bot_user')
    db_password = os.getenv('DB_PASSWORD', 'password')
    
    if all([db_host, db_port, db_name, db_user, db_password]):
        return f"postgresql+asyncpg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    
    # Fall back to config file
    return config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schemas if using multiple schemas
        include_schemas=True,
        # Compare server defaults
        compare_server_default=True,
        # Compare types
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """
    Run migrations with the given connection.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Include schemas if using multiple schemas
        include_schemas=True,
        # Compare server defaults
        compare_server_default=True,
        # Compare types
        compare_type=True,
        # Render as batch for SQLite compatibility (if needed)
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Run migrations in 'online' mode with async engine.

    In this scenario we need to create an Engine
    and associate a connection with the context.
    """
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = create_async_engine(
        configuration["sqlalchemy.url"],
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()