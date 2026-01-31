"""outfit match job

Revision ID: 0020_outfit_match_job
Revises: 0019_item_wear_log_source_outfit
Create Date: 2026-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0020_outfit_match_job"
down_revision = "0019_item_wear_log_source_outfit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outfit_match_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_url", sa.Text(), nullable=False),
        sa.Column("worn_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("matches_json", sa.JSON(), nullable=True),
        sa.Column("slots_json", sa.JSON(), nullable=True),
        sa.Column("warnings_json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("min_confidence", sa.Float(), nullable=True),
        sa.Column("max_per_slot", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("outfit_match_job")
