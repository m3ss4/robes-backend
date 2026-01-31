"""packing cubes

Revision ID: 0022_packing_cubes
Revises: 0021_outfit_wear_log_photo_id
Create Date: 2026-02-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0022_packing_cubes"
down_revision = "0021_outfit_wear_log_photo_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "packing_cube",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("cube_type", sa.String(length=16), nullable=False),
        sa.Column("weather_tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_table(
        "packing_cube_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("cube_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["cube_id"], ["packing_cube.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["item_id"], ["item.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("cube_id", "item_id", name="uq_packing_cube_item"),
    )


def downgrade() -> None:
    op.drop_table("packing_cube_item")
    op.drop_table("packing_cube")
