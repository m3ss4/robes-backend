"""add item_image view

Revision ID: 0004_item_image_view
Revises: 0003_item_attributes_and_audit
Create Date: 2025-12-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_item_image_view"
down_revision = "0003_item_attributes_and_audit"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("item_image", sa.Column("view", sa.String(length=16), nullable=True, server_default="front"))
    op.execute("UPDATE item_image SET view='front' WHERE view IS NULL;")
    op.alter_column("item_image", "view", nullable=False, server_default=None)


def downgrade() -> None:
    op.drop_column("item_image", "view")
