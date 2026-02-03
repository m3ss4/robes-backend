"""wardrobe quality scores and suggestions

Revision ID: 0023_wardrobe_quality
Revises: 0022_packing_cubes
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023_wardrobe_quality"
down_revision = "0022_packing_cubes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add quality_preferences to user table
    op.add_column("user", sa.Column("quality_preferences", postgresql.JSON(), nullable=True))

    # Create wardrobe_quality_score table
    op.create_table(
        "wardrobe_quality_score",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("versatility_score", sa.Float(), nullable=False),
        sa.Column("utilization_score", sa.Float(), nullable=False),
        sa.Column("completeness_score", sa.Float(), nullable=False),
        sa.Column("balance_score", sa.Float(), nullable=False),
        sa.Column("diversity_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("explanations", postgresql.JSON(), nullable=True),
        sa.Column("items_count", sa.Integer(), nullable=False),
        sa.Column("outfits_count", sa.Integer(), nullable=False),
        sa.Column("wear_logs_count", sa.Integer(), nullable=False),
        sa.Column("diversity_config_snapshot", postgresql.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wardrobe_quality_score_user_computed",
        "wardrobe_quality_score",
        ["user_id", "computed_at"],
    )

    # Create wardrobe_quality_suggestion table
    op.create_table(
        "wardrobe_quality_suggestion",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("score_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("suggestion_type", sa.String(length=32), nullable=False),
        sa.Column("dimension", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("why", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("expected_impact", sa.Float(), nullable=True),
        sa.Column("related_item_ids", postgresql.JSON(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["score_id"], ["wardrobe_quality_score.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_wardrobe_quality_suggestion_user_status",
        "wardrobe_quality_suggestion",
        ["user_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_wardrobe_quality_suggestion_user_status")
    op.drop_table("wardrobe_quality_suggestion")
    op.drop_index("ix_wardrobe_quality_score_user_computed")
    op.drop_table("wardrobe_quality_score")
    op.drop_column("user", "quality_preferences")
