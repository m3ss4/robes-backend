"""multiuser core

Revision ID: 0007_multiuser_core
Revises: 0006_item_image_r2_keys
Create Date: 2025-12-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_multiuser_core"
down_revision = "0006_item_image_r2_keys"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS "user" (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            email text UNIQUE,
            name text,
            avatar_url text,
            password_hash text,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS account (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            user_id uuid NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
            provider text NOT NULL,
            provider_user_id text NOT NULL,
            raw_profile jsonb,
            CONSTRAINT uq_account_provider_subject UNIQUE (provider, provider_user_id)
        );
        """
    )
    op.execute(
        'ALTER TABLE item ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES "user"(id) ON DELETE CASCADE;'
    )
    op.execute(
        "ALTER TABLE item ADD COLUMN IF NOT EXISTS status varchar(32) DEFAULT 'active';"
    )
    op.execute(
        'ALTER TABLE item_image ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES "user"(id) ON DELETE CASCADE;'
    )


def downgrade() -> None:
    op.drop_column("item_image", "user_id")
    op.drop_column("item", "user_id")
    op.drop_table("account")
    op.drop_table("user")
