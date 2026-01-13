"""tag indexes

Revision ID: 0002_tag_indexes
Revises: 0001_init
Create Date: 2025-12-17
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "0002_tag_indexes"
down_revision = "0001_init"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_item_style_tags  ON item USING GIN (style_tags);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_item_event_tags  ON item USING GIN (event_tags);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_item_season_tags ON item USING GIN (season_tags);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_item_season_tags;")
    op.execute("DROP INDEX IF EXISTS idx_item_event_tags;")
    op.execute("DROP INDEX IF EXISTS idx_item_style_tags;")
