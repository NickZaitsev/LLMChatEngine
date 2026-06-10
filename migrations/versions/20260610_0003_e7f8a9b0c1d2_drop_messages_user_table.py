"""Drop messages_user table.

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-06-10 00:03:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("messages_user")


def downgrade() -> None:
    op.create_table(
        "messages_user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("bot_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_user_user_id", "messages_user", ["user_id"], unique=False)
    op.create_index("ix_messages_user_created_at", "messages_user", ["created_at"], unique=False)
    op.create_index("ix_messages_user_user_bot", "messages_user", ["user_id", "bot_id"], unique=False)
