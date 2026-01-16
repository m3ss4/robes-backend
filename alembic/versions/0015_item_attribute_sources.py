"""item attribute sources

Revision ID: 0015_item_attribute_sources
Revises: 0014_wear_log_soft_delete
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_item_attribute_sources"
down_revision = "0014_wear_log_soft_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item", sa.Column("attribute_sources", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("item", "attribute_sources")
