"""audit provider

Revision ID: 0005_audit_provider
Revises: 0004_item_image_view
Create Date: 2025-12-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_audit_provider"
down_revision = "0004_item_image_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_suggestion_audit", sa.Column("provider", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("item_suggestion_audit", "provider")
