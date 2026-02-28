"""add_multibot_tables

Revision ID: 7890abcdef12
Revises: 619d48a9dd9c
Create Date: 2026-01-02 16:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '7890abcdef12'
down_revision: Union[str, None] = '619d48a9dd9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create bots table
    op.create_table('bots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('token_encrypted', sa.Text(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('personality', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('feature_flags', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('llm_config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # Create user_bot_settings table
    op.create_table('user_bot_settings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('bot_id', sa.UUID(), nullable=False),
        sa.Column('settings', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['bot_id'], ['bots.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_user_bot_settings_user_bot', 'user_bot_settings', ['user_id', 'bot_id'], unique=True)

    # Add bot_id to conversations
    op.add_column('conversations', sa.Column('bot_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'conversations', 'bots', ['bot_id'], ['id'], ondelete='CASCADE')

    # Add bot_id to memories
    op.add_column('memories', sa.Column('bot_id', sa.UUID(), nullable=True))
    op.create_index('ix_memories_bot_id', 'memories', ['bot_id'], unique=False)
    op.create_foreign_key(None, 'memories', 'bots', ['bot_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # Remove bot_id from memories
    op.drop_constraint(None, 'memories', type_='foreignkey')
    op.drop_index('ix_memories_bot_id', table_name='memories')
    op.drop_column('memories', 'bot_id')

    # Remove bot_id from conversations
    op.drop_constraint(None, 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'bot_id')

    # Drop user_bot_settings table
    op.drop_index('ix_user_bot_settings_user_bot', table_name='user_bot_settings')
    op.drop_table('user_bot_settings')

    # Drop bots table
    op.drop_table('bots')
