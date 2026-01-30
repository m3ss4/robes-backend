"""fix embedding column type for pgvector

Revision ID: 0018_fix_embedding_vector_type
Revises: 0017_outfit_photo_flow
Create Date: 2026-01-22
"""
from alembic import op

revision = "0018_fix_embedding_vector_type"
down_revision = "0017_outfit_photo_flow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'item_image_features'
                  AND column_name = 'embedding'
                  AND udt_name = '_float8'
            ) THEN
                ALTER TABLE item_image_features
                ALTER COLUMN embedding TYPE vector(512)
                USING embedding::vector;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # No safe automatic downgrade from vector to float8[]
    pass
