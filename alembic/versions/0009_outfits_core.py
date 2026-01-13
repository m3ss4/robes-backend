"""outfits core

Revision ID: 0009_outfits_core
Revises: 0008_item_status_and_delete
Create Date: 2026-01-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_outfits_core"
down_revision = "0008_item_status_and_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outfit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="user_saved"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("primary_image_url", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_user_id", "outfit", ["user_id"])

    op.create_table(
        "outfit_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("item.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slot", sa.String(length=32), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_item_outfit_id", "outfit_item", ["outfit_id"])
    op.create_index("ix_outfit_item_item_id", "outfit_item", ["item_id"])

    op.create_table(
        "outfit_revision",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rev_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("items_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attributes_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metrics_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_revision_outfit_id", "outfit_revision", ["outfit_id"])

    op.create_table(
        "outfit_wear_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit.id", ondelete="CASCADE"), nullable=False),
        sa.Column("outfit_revision_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit_revision.id", ondelete="SET NULL"), nullable=True),
        sa.Column("worn_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("event", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("weather", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("season", sa.Text(), nullable=True),
        sa.Column("mood", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_wear_log_user_id", "outfit_wear_log", ["user_id"])
    op.create_index("ix_outfit_wear_log_outfit_id", "outfit_wear_log", ["outfit_id"])

    op.create_table(
        "outfit_wear_log_item",
        sa.Column("wear_log_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit_wear_log.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("item.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("slot", sa.String(length=32), nullable=False),
    )

    op.create_table(
        "suggest_session",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("candidate_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cursor", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_info", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_suggest_session_user_id", "suggest_session", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_suggest_session_user_id", table_name="suggest_session")
    op.drop_table("suggest_session")
    op.drop_table("outfit_wear_log_item")
    op.drop_index("ix_outfit_wear_log_outfit_id", table_name="outfit_wear_log")
    op.drop_index("ix_outfit_wear_log_user_id", table_name="outfit_wear_log")
    op.drop_table("outfit_wear_log")
    op.drop_index("ix_outfit_revision_outfit_id", table_name="outfit_revision")
    op.drop_table("outfit_revision")
    op.drop_index("ix_outfit_item_item_id", table_name="outfit_item")
    op.drop_index("ix_outfit_item_outfit_id", table_name="outfit_item")
    op.drop_table("outfit_item")
    op.drop_index("ix_outfit_user_id", table_name="outfit")
    op.drop_table("outfit")
