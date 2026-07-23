"""add books table

Revision ID: c9d0e1f2a3b4
Revises: b7c8d9e0f1a2
Create Date: 2026-06-10

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'c9d0e1f2a3b4'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'books',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('bot_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('author', sa.String(length=255), nullable=True),
        sa.Column('source_filename', sa.String(length=500), nullable=False),
        sa.Column('file_format', sa.String(length=10), nullable=False),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='pending', nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('chunk_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('char_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bot_id'], ['bots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_books_bot_id', 'books', ['bot_id'], unique=False)
    op.create_index('ix_books_bot_hash', 'books', ['bot_id', 'file_hash'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_books_bot_hash', table_name='books')
    op.drop_index('ix_books_bot_id', table_name='books')
    op.drop_table('books')
