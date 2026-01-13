"""initial

Revision ID: 0001_init
Revises: 
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa
import uuid
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001_init'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.create_table('item',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('kind', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('brand', sa.String(length=200), nullable=True),
        sa.Column('base_color', sa.String(length=64), nullable=True),
        sa.Column('material', sa.String(length=128), nullable=True),
        sa.Column('warmth', sa.Integer(), nullable=True),
        sa.Column('formality', sa.Float(), nullable=True),
        sa.Column('style_tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('event_tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('season_tags', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )
    op.create_table('item_image',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('item_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('item.id', ondelete='CASCADE'), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('bg_removed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )

def downgrade() -> None:
    op.drop_table('item_image')
    op.drop_table('item')
