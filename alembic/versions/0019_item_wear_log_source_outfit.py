"""Add source_outfit_log_id to item_wear_log

Revision ID: 0019_item_wear_log_source_outfit
Revises: 0018_fix_embedding_vector_type
Create Date: 2026-01-30
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0019_item_wear_log_source_outfit"
down_revision = "0018_fix_embedding_vector_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "item_wear_log",
        sa.Column("source_outfit_log_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "item_wear_log_source_outfit_log_id_fkey",
        "item_wear_log",
        "outfit_wear_log",
        ["source_outfit_log_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("item_wear_log_source_outfit_log_id_fkey", "item_wear_log", type_="foreignkey")
    op.drop_column("item_wear_log", "source_outfit_log_id")
