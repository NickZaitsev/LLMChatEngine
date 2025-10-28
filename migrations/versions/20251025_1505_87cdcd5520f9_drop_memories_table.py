"""Drop memories table

Revision ID: 87cdcd5520f9
Revises: 001
Create Date: 2025-10-25 15:05:00.773598+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '87cdcd5520f9'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('memories')


def downgrade() -> None:
    op.create_table('memories',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('conversation_id', sa.UUID(), nullable=False),
    sa.Column('memory_type', sa.VARCHAR(length=50), nullable=False),
    sa.Column('text', sa.TEXT(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('embedding', sa.TEXT(), nullable=True),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )