"""Make conversation persona nullable.

Revision ID: d4e5f6a7b8c9
Revises: c9d0e1f2a3b4
Create Date: 2026-06-10 00:02:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("conversations_persona_id_fkey", "conversations", type_="foreignkey")
    op.alter_column(
        "conversations",
        "persona_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.create_foreign_key(
        "conversations_persona_id_fkey",
        "conversations",
        "personas",
        ["persona_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("conversations_persona_id_fkey", "conversations", type_="foreignkey")
    op.alter_column(
        "conversations",
        "persona_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.create_foreign_key(
        "conversations_persona_id_fkey",
        "conversations",
        "personas",
        ["persona_id"],
        ["id"],
        ondelete="CASCADE",
    )
