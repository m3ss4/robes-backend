"""outfit wear log photo id

Revision ID: 0021_outfit_wear_log_photo_id
Revises: 0020_outfit_match_job
Create Date: 2026-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0021_outfit_wear_log_photo_id"
down_revision = "0020_outfit_match_job"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outfit_wear_log",
        sa.Column("outfit_photo_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_outfit_wear_log_outfit_photo_id",
        "outfit_wear_log",
        "outfit_photo",
        ["outfit_photo_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_outfit_wear_log_outfit_photo_id", "outfit_wear_log", type_="foreignkey")
    op.drop_column("outfit_wear_log", "outfit_photo_id")
