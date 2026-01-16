"""wear log soft delete

Revision ID: 0014_wear_log_soft_delete
Revises: 0013_password_reset_tokens
Create Date: 2026-01-15
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_wear_log_soft_delete"
down_revision = "0013_password_reset_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("outfit_wear_log", sa.Column("source", sa.Text(), nullable=True))
    op.add_column("outfit_wear_log", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("item_wear_log", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint("uq_outfit_wear_log_user_outfit_date", "outfit_wear_log", type_="unique")
    op.drop_constraint("uq_item_wear_log_user_item_date", "item_wear_log", type_="unique")

    op.create_index(
        "ix_outfit_wear_log_user_outfit_date_active",
        "outfit_wear_log",
        ["user_id", "outfit_id", "worn_date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_item_wear_log_user_item_date_active",
        "item_wear_log",
        ["user_id", "item_id", "worn_date"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_item_wear_log_user_item_date_active", table_name="item_wear_log")
    op.drop_index("ix_outfit_wear_log_user_outfit_date_active", table_name="outfit_wear_log")

    op.create_unique_constraint(
        "uq_outfit_wear_log_user_outfit_date",
        "outfit_wear_log",
        ["user_id", "outfit_id", "worn_date"],
    )
    op.create_unique_constraint(
        "uq_item_wear_log_user_item_date",
        "item_wear_log",
        ["user_id", "item_id", "worn_date"],
    )

    op.drop_column("item_wear_log", "deleted_at")
    op.drop_column("outfit_wear_log", "deleted_at")
    op.drop_column("outfit_wear_log", "source")
