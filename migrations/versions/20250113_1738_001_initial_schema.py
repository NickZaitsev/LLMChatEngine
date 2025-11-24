"""Initial schema with users, personas, conversations, messages, and memories

Revision ID: 001
Revises: 
Create Date: 2025-01-13 17:38:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from config import MEMORY_EMBED_DIM
# Try to import pgvector, but handle gracefully if not available
try:
    from pgvector.sqlalchemy import Vector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False
    Vector = None

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema"""
    
    # Enable pgvector extension if available
    if PGVECTOR_AVAILABLE:
        op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    
    # Create users table
    op.create_table('users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('extra_data', sa.JSON(), nullable=False, default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username')
    )
    
    # Create personas table
    op.create_table('personas',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False, default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create conversations table
    op.create_table('conversations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('persona_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=True),
        sa.Column('extra_data', sa.JSON(), nullable=False, default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.text('now()')),
        sa.ForeignKeyConstraint(['persona_id'], ['personas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create messages table
    op.create_table('messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
        sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('extra_data', sa.JSON(), nullable=False, default=sa.text("'{}'::jsonb")),
        sa.Column('token_count', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.text('now()')),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for messages table
    op.create_index('ix_messages_conversation_created_at', 'messages', ['conversation_id', 'created_at'])
    op.create_index('ix_messages_conversation_role', 'messages', ['conversation_id', 'role'])
    
    # Create memories table
    if PGVECTOR_AVAILABLE and Vector:
        # With pgvector support
        op.create_table('memories',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
            sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('memory_type', sa.String(length=50), nullable=False, default='episodic'),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.text('now()')),
            sa.Column('embedding', Vector(MEMORY_EMBED_DIM), nullable=True),
            sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create vector similarity index
        op.create_index('ix_memories_embedding', 'memories', ['embedding'], 
                       postgresql_using='ivfflat', postgresql_with={'lists': 100})
    else:
        # Fallback without pgvector
        op.create_table('memories',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, default=sa.text('gen_random_uuid()')),
            sa.Column('conversation_id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('memory_type', sa.String(length=50), nullable=False, default='episodic'),
            sa.Column('text', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, default=sa.text('now()')),
            sa.Column('embedding', sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id')
        )
    
    # Create index for memories table  
    op.create_index('ix_memories_conversation_type', 'memories', ['conversation_id', 'memory_type'])


def downgrade() -> None:
    """Drop all tables and extensions"""
    
    # Drop tables in reverse order
    op.drop_table('memories')
    op.drop_table('messages')
    op.drop_table('conversations')
    op.drop_table('personas')
    op.drop_table('users')
    
    # Optionally drop pgvector extension (commented out to be safe)
    # op.execute('DROP EXTENSION IF EXISTS pgvector')