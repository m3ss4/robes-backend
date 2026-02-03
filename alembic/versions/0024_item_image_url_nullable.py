"""allow item_image url to be nullable

Revision ID: 0024_item_image_url_nullable
Revises: 0023_wardrobe_quality
Create Date: 2026-01-31 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "0024_item_image_url_nullable"
down_revision = "0023_wardrobe_quality"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("item_image", "url", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.alter_column("item_image", "url", existing_type=sa.Text(), nullable=False)
