"""item image r2 keys

Revision ID: 0006_item_image_r2_keys
Revises: 0005_audit_provider
Create Date: 2025-12-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_item_image_r2_keys"
down_revision = "0005_audit_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("item_image", sa.Column("bucket", sa.Text(), nullable=True))
    op.add_column("item_image", sa.Column("key", sa.Text(), nullable=True))
    op.add_column("item_image", sa.Column("bytes", sa.Integer(), nullable=True))
    op.add_column("item_image", sa.Column("kind", sa.Text(), nullable=False, server_default="original"))
    op.add_column("item_image", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("item_image", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column(
        "item_image",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_item_image_item_id_kind", "item_image", ["item_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_item_image_item_id_kind", table_name="item_image")
    op.drop_column("item_image", "created_at")
    op.drop_column("item_image", "height")
    op.drop_column("item_image", "width")
    op.drop_column("item_image", "kind")
    op.drop_column("item_image", "bytes")
    op.drop_column("item_image", "key")
    op.drop_column("item_image", "bucket")
