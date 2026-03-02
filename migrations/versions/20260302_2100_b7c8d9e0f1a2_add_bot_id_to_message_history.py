"""add bot_id to message history tables

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-02

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c8d9e0f1a2'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('messages_log', sa.Column('bot_id', sa.UUID(), nullable=True))
    op.add_column('messages_user', sa.Column('bot_id', sa.UUID(), nullable=True))

    op.create_foreign_key(
        'fk_messages_log_bot_id',
        'messages_log', 'bots',
        ['bot_id'], ['id'],
        ondelete='CASCADE'
    )
    op.create_foreign_key(
        'fk_messages_user_bot_id',
        'messages_user', 'bots',
        ['bot_id'], ['id'],
        ondelete='CASCADE'
    )

    op.create_index('ix_messages_log_user_bot', 'messages_log', ['user_id', 'bot_id'], unique=False)
    op.create_index('ix_messages_user_user_bot', 'messages_user', ['user_id', 'bot_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_messages_user_user_bot', table_name='messages_user')
    op.drop_index('ix_messages_log_user_bot', table_name='messages_log')
    op.drop_constraint('fk_messages_user_bot_id', 'messages_user', type_='foreignkey')
    op.drop_constraint('fk_messages_log_bot_id', 'messages_log', type_='foreignkey')
    op.drop_column('messages_user', 'bot_id')
    op.drop_column('messages_log', 'bot_id')
