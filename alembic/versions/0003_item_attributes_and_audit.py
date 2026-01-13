"""item attributes + suggestion audit

Revision ID: 0003_item_attributes_and_audit
Revises: 0002_tag_indexes
Create Date: 2025-12-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_item_attributes_and_audit"
down_revision = "0002_tag_indexes"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("item", sa.Column("category", sa.String(length=32), nullable=True))
    op.add_column("item", sa.Column("item_type", sa.String(length=64), nullable=True))
    op.add_column("item", sa.Column("fit", sa.String(length=64), nullable=True))
    op.add_column("item", sa.Column("fabric_kind", sa.String(length=64), nullable=True))
    op.add_column("item", sa.Column("pattern", sa.String(length=64), nullable=True))
    op.add_column("item", sa.Column("tone", sa.String(length=32), nullable=True))
    op.add_column("item", sa.Column("layer_role", sa.String(length=32), nullable=True))

    op.create_table(
        "item_suggestion_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_ref", sa.Text(), nullable=True),
        sa.Column("hints", postgresql.JSONB(), nullable=True),
        sa.Column("draft", postgresql.JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("llm_used", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("llm_tokens", sa.Integer(), nullable=True),
    )

def downgrade() -> None:
    op.drop_table("item_suggestion_audit")
    op.drop_column("item", "layer_role")
    op.drop_column("item", "tone")
    op.drop_column("item", "pattern")
    op.drop_column("item", "fabric_kind")
    op.drop_column("item", "fit")
    op.drop_column("item", "item_type")
    op.drop_column("item", "category")
