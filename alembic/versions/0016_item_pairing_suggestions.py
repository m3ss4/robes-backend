"""item pairing suggestions

Revision ID: 0016_item_pairing_suggestions
Revises: 0015_item_attribute_sources
Create Date: 2026-01-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_item_pairing_suggestions"
down_revision = "0015_item_attribute_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item", sa.Column("pairing_suggestions", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("item", "pairing_suggestions")
