"""outfit photo analysis flow

Revision ID: 0017_outfit_photo_flow
Revises: 0016_item_pairing_suggestions
Create Date: 2026-01-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_outfit_photo_flow"
down_revision = "0016_item_pairing_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outfit_photo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=True),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("image_hash", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_photo_user", "outfit_photo", ["user_id"])
    op.create_index("ix_outfit_photo_status", "outfit_photo", ["status"])

    op.create_table(
        "outfit_photo_analysis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("outfit_photo_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("outfit_photo.id", ondelete="CASCADE")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.Text(), nullable=False, server_default="clip_embed_v1"),
        sa.Column("candidates_json", sa.JSON(), nullable=True),
        sa.Column("matched_items_json", sa.JSON(), nullable=True),
        sa.Column("matched_outfit_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=True),
        sa.Column("debug_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_outfit_photo_analysis_photo", "outfit_photo_analysis", ["outfit_photo_id"])
    op.create_index("ix_outfit_photo_analysis_user", "outfit_photo_analysis", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_outfit_photo_analysis_user", table_name="outfit_photo_analysis")
    op.drop_index("ix_outfit_photo_analysis_photo", table_name="outfit_photo_analysis")
    op.drop_table("outfit_photo_analysis")
    op.drop_index("ix_outfit_photo_status", table_name="outfit_photo")
    op.drop_index("ix_outfit_photo_user", table_name="outfit_photo")
    op.drop_table("outfit_photo")
