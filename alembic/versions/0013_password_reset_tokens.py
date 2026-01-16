"""password reset tokens

Revision ID: 0013_password_reset_tokens
Revises: 0012_outfit_feedback
Create Date: 2026-01-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013_password_reset_tokens"
down_revision = "0012_outfit_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_password_reset_token_user_id", "password_reset_token", ["user_id"])
    op.create_index("ix_password_reset_token_expires_at", "password_reset_token", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_token_expires_at", table_name="password_reset_token")
    op.drop_index("ix_password_reset_token_user_id", table_name="password_reset_token")
    op.drop_table("password_reset_token")
