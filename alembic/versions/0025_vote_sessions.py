"""add vote sessions and votes

Revision ID: 0025_vote_sessions
Revises: 0024_item_image_url_nullable
Create Date: 2026-02-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025_vote_sessions"
down_revision = "0024_item_image_url_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vote_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("share_code", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_vote_session_share_code", "vote_session", ["share_code"], unique=True)

    op.create_table(
        "vote_session_outfit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vote_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("session_id", "outfit_id", name="uq_vote_session_outfit"),
    )
    op.create_index(
        "ix_vote_session_outfit_session_position",
        "vote_session_outfit",
        ["session_id", "position"],
        unique=False,
    )

    op.create_table(
        "vote",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vote_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("voter_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("session_id", "voter_hash", name="uq_vote_session_voter"),
    )
    op.create_index("ix_vote_session_outfit", "vote", ["session_id", "outfit_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_vote_session_outfit", table_name="vote")
    op.drop_table("vote")
    op.drop_index("ix_vote_session_outfit_session_position", table_name="vote_session_outfit")
    op.drop_table("vote_session_outfit")
    op.drop_index("ix_vote_session_share_code", table_name="vote_session")
    op.drop_table("vote_session")
