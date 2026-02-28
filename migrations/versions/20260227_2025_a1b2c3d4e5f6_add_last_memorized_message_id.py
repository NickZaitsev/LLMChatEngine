"""add last_memorized_message_id to conversations

Revision ID: a1b2c3d4e5f6
Revises: 619d48a9dd9c
Create Date: 2026-02-27

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '7890abcdef12'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'conversations',
        sa.Column('last_memorized_message_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_conv_last_memorized_msg',
        'conversations', 'messages',
        ['last_memorized_message_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_conv_last_memorized_msg', 'conversations', type_='foreignkey')
    op.drop_column('conversations', 'last_memorized_message_id')
