"""outfit feedback

Revision ID: 0012_outfit_feedback
Revises: 0011_wear_logs_per_day
Create Date: 2026-01-14
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_outfit_feedback"
down_revision = "0011_wear_logs_per_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outfit") as batch_op:
        batch_op.add_column(sa.Column("feedback", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("outfit") as batch_op:
        batch_op.drop_column("feedback")
