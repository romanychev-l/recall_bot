"""Persistent group reports and voluntary memberships."""
from alembic import op
import sqlalchemy as sa
from bot.db.models import UtcDateTime

revision = "b731d4e1a920"
down_revision = "87e122489a6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_chats",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("creator_id", sa.BigInteger(), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("report_time", sa.String(5), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("bot_present", sa.Boolean(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.Integer(), nullable=True),
        sa.Column("next_report_at", UtcDateTime(), nullable=False),
        sa.Column("created_at", UtcDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_group_chats"),
    )
    op.create_index("ix_group_chats_enabled_bot_present_next_report_at", "group_chats",
                    ["enabled", "bot_present", "next_report_at"])
    op.create_table(
        "group_members",
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("joined_at", UtcDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["chat_id"], ["group_chats.id"],
                                name="fk_group_members_chat_id_group_chats", ondelete="CASCADE", onupdate="CASCADE"),
        sa.PrimaryKeyConstraint("chat_id", "user_id", name="pk_group_members"),
    )


def downgrade() -> None:
    op.drop_table("group_members")
    op.drop_index("ix_group_chats_enabled_bot_present_next_report_at", table_name="group_chats")
    op.drop_table("group_chats")
