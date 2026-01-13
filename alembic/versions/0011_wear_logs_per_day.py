"""wear logs per day uniqueness

Revision ID: 0011_wear_logs_per_day
Revises: 0010_feature_store
Create Date: 2026-01-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_wear_logs_per_day"
down_revision = "0010_feature_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Outfit wear log: add worn_date and unique constraint
    with op.batch_alter_table("outfit_wear_log") as batch_op:
        batch_op.add_column(sa.Column("worn_date", sa.Date(), nullable=True))
    op.create_unique_constraint("uq_outfit_wear_log_user_outfit_date", "outfit_wear_log", ["user_id", "outfit_id", "worn_date"])

    # Item wear log table
    op.create_table(
        "item_wear_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("item.id", ondelete="CASCADE")),
        sa.Column("worn_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("worn_date", sa.Date(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "item_id", "worn_date", name="uq_item_wear_log_user_item_date"),
    )
    op.create_index("ix_item_wear_log_user_date", "item_wear_log", ["user_id", "worn_date"])
    op.create_index("ix_item_wear_log_user_item", "item_wear_log", ["user_id", "item_id"])


def downgrade() -> None:
    op.drop_index("ix_item_wear_log_user_item", table_name="item_wear_log")
    op.drop_index("ix_item_wear_log_user_date", table_name="item_wear_log")
    op.drop_table("item_wear_log")
    op.drop_constraint("uq_outfit_wear_log_user_outfit_date", "outfit_wear_log", type_="unique")
    with op.batch_alter_table("outfit_wear_log") as batch_op:
        batch_op.drop_column("worn_date")
