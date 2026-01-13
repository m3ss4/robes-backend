"""item status and delete prep

Revision ID: 0008_item_status_and_delete
Revises: 0007_multiuser_core
Create Date: 2025-12-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_item_status_and_delete"
down_revision = "0007_multiuser_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE item ADD COLUMN IF NOT EXISTS status varchar(32) DEFAULT 'active';")
    op.execute("UPDATE item SET status='active' WHERE status IS NULL;")


def downgrade() -> None:
    op.drop_column("item", "status")
