"""current telegram bot schema

Revision ID: 0001_current_schema
Revises:
Create Date: 2026-04-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0001_current_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("first_name", sa.String(), nullable=True),
        sa.Column("last_name", sa.String(), nullable=True),
        sa.Column("language_code", sa.String(), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        sa.Column("is_premium", sa.Boolean(), nullable=True),
        sa.Column("added_to_attachment_menu", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("user_state", sa.String(), nullable=True),
        sa.Column("user_role", sa.String(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("total_messages", sa.Integer(), nullable=False),
        sa.Column("total_commands", sa.Integer(), nullable=False),
        sa.Column("first_interaction", sa.DateTime(), nullable=True),
        sa.Column("last_interaction", sa.DateTime(), nullable=True),
        sa.Column("current_session_id", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("idx_created_at", "users", ["created_at"], unique=False)
    op.create_index("idx_is_active", "users", ["is_active"], unique=False)
    op.create_index("idx_last_seen", "users", ["last_seen"], unique=False)
    op.create_index("idx_user_role", "users", ["user_role"], unique=False)
    op.create_index("idx_username", "users", ["username"], unique=False)

    op.create_table(
        "user_activities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activity_type", sa.String(), nullable=False),
        sa.Column("activity_data", sa.Text(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_activity_session", "user_activities", ["session_id"], unique=False
    )
    op.create_index(
        "idx_activity_timestamp", "user_activities", ["timestamp"], unique=False
    )
    op.create_index(
        "idx_activity_type", "user_activities", ["activity_type"], unique=False
    )
    op.create_index(
        "idx_activity_user_id", "user_activities", ["user_id"], unique=False
    )

    op.create_table(
        "chat_sessions",
        sa.Column("session_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("last_activity", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(
        "idx_chat_sessions_created_at", "chat_sessions", ["created_at"], unique=False
    )
    op.create_index(
        "idx_chat_sessions_deleted_at", "chat_sessions", ["deleted_at"], unique=False
    )
    op.create_index(
        "idx_chat_sessions_last_activity",
        "chat_sessions",
        ["last_activity"],
        unique=False,
    )
    op.create_index(
        "idx_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_index("idx_chat_sessions_last_activity", table_name="chat_sessions")
    op.drop_index("idx_chat_sessions_deleted_at", table_name="chat_sessions")
    op.drop_index("idx_chat_sessions_created_at", table_name="chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_index("idx_activity_user_id", table_name="user_activities")
    op.drop_index("idx_activity_type", table_name="user_activities")
    op.drop_index("idx_activity_timestamp", table_name="user_activities")
    op.drop_index("idx_activity_session", table_name="user_activities")
    op.drop_table("user_activities")

    op.drop_index("idx_username", table_name="users")
    op.drop_index("idx_user_role", table_name="users")
    op.drop_index("idx_last_seen", table_name="users")
    op.drop_index("idx_is_active", table_name="users")
    op.drop_index("idx_created_at", table_name="users")
    op.drop_table("users")
