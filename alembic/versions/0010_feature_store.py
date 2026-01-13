"""feature store and pgvector

Revision ID: 0010_feature_store
Revises: 0009_outfits_core
Create Date: 2026-01-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_feature_store"
down_revision = "0009_outfits_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable pgvector extension (safe if already present)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "item_image_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("image_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("item_image.id", ondelete="CASCADE"), nullable=False),
        sa.Column("features_version", sa.Text(), nullable=False),
        sa.Column("dominant_color_name", sa.Text(), nullable=True),
        sa.Column("dominant_color_hex", sa.Text(), nullable=True),
        sa.Column("palette_hex", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("brightness", sa.Float(), nullable=True),
        sa.Column("saturation", sa.Float(), nullable=True),
        sa.Column("edge_density", sa.Float(), nullable=True),
        sa.Column("stripe_score", sa.Float(), nullable=True),
        sa.Column("plaid_score", sa.Float(), nullable=True),
        sa.Column("dot_score", sa.Float(), nullable=True),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True),
        sa.Column("family_pred", sa.Text(), nullable=True),
        sa.Column("family_p", sa.Float(), nullable=True),
        sa.Column("type_pred", sa.Text(), nullable=True),
        sa.Column("type_p", sa.Float(), nullable=True),
        sa.Column("type_top3", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pattern_pred", sa.Text(), nullable=True),
        sa.Column("pattern_p", sa.Float(), nullable=True),
        sa.Column("pattern_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("image_sha256", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("image_id", "features_version", name="uq_item_image_features_image_version"),
    )
    op.create_index("ix_item_image_features_image", "item_image_features", ["image_id"])
    op.create_index("ix_item_image_features_sha", "item_image_features", ["image_sha256"])

    # Optional rollups on item
    with op.batch_alter_table("item") as batch_op:
        batch_op.add_column(sa.Column("dominant_color_name", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("palette_hex", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("last_features_at", sa.DateTime(timezone=True), nullable=True))
    # Extend audit table
    with op.batch_alter_table("item_suggestion_audit") as batch_op:
        batch_op.add_column(sa.Column("family_pred", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("family_p", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("type_pred", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("type_p", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("type_top3", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("pattern_pred", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("pattern_p", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("pattern_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("feature_wait_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("feature_source", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("image_count", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("had_family_hint", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("item") as batch_op:
        batch_op.drop_column("last_features_at")
        batch_op.drop_column("palette_hex")
        batch_op.drop_column("dominant_color_name")

    op.drop_index("ix_item_image_features_sha", table_name="item_image_features")
    op.drop_index("ix_item_image_features_image", table_name="item_image_features")
    op.drop_table("item_image_features")
