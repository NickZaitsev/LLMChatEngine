"""add bot_id to message history tables

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-03-02

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


LEGACY_MESSAGE_TABLES = (
    ("messages_log", "fk_messages_log_bot_id", "ix_messages_log_user_bot"),
    ("messages_user", "fk_messages_user_bot_id", "ix_messages_user_user_bot"),
)


def upgrade() -> None:
    """Upgrade legacy message tables when they are present.

    The canonical schema stores history in ``messages``; these two tables only
    exist in older deployments, so a fresh install must skip them.
    """
    inspector = sa.inspect(op.get_bind())
    for table_name, constraint_name, index_name in LEGACY_MESSAGE_TABLES:
        if not inspector.has_table(table_name):
            continue
        op.add_column(table_name, sa.Column("bot_id", sa.UUID(), nullable=True))
        op.create_foreign_key(
            constraint_name,
            table_name,
            "bots",
            ["bot_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            index_name,
            table_name,
            ["user_id", "bot_id"],
            unique=False,
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table_name, constraint_name, index_name in reversed(LEGACY_MESSAGE_TABLES):
        if not inspector.has_table(table_name):
            continue
        op.drop_index(index_name, table_name=table_name)
        op.drop_constraint(constraint_name, table_name, type_="foreignkey")
        op.drop_column(table_name, "bot_id")
