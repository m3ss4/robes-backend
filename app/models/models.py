from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func
import uuid
from datetime import datetime, date
from app.core.db import Base
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa
try:
    from pgvector.sqlalchemy import Vector as PgVector  # type: ignore

    def Vector(dim: int):
        return PgVector(dim)

except Exception:  # pragma: no cover - fallback when pgvector not installed
    from sqlalchemy import ARRAY, Float

    def Vector(dim: int):
        return ARRAY(Float)

class Item(Base):
    __tablename__ = "item"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    attribute_sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    item_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    fabric_kind: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    layer_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    name: Mapped[str | None] = mapped_column(String(200))
    brand: Mapped[str | None] = mapped_column(String(200))
    base_color: Mapped[str | None] = mapped_column(String(64))
    material: Mapped[str | None] = mapped_column(String(128))
    warmth: Mapped[int | None] = mapped_column(Integer)
    formality: Mapped[float | None] = mapped_column(Float)
    style_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    event_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    season_tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    images: Mapped[list["ItemImage"]] = relationship(
        "ItemImage",
        back_populates="item",
        lazy="selectin",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class ItemImage(Base):
    __tablename__ = "item_image"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    url: Mapped[str] = mapped_column(Text)
    bg_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    view: Mapped[str] = mapped_column(String(16), default="front")
    bucket: Mapped[str | None] = mapped_column(Text, nullable=True)
    key: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(Text, default="original")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    item: Mapped["Item"] = relationship("Item", back_populates="images")

class ItemImageFeatures(Base):
    __tablename__ = "item_image_features"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    image_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item_image.id", ondelete="CASCADE"), nullable=False)
    features_version: Mapped[str] = mapped_column(Text, nullable=False)
    dominant_color_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    dominant_color_hex: Mapped[str | None] = mapped_column(Text, nullable=True)
    palette_hex: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    brightness: Mapped[float | None] = mapped_column(Float, nullable=True)
    saturation: Mapped[float | None] = mapped_column(Float, nullable=True)
    edge_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    stripe_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    plaid_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dot_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedding = mapped_column(Vector(512), nullable=True)
    family_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    family_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_top3: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pattern_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    image_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Outfit(Base):
    __tablename__ = "outfit"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="user_saved")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attributes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    items: Mapped[list["OutfitItem"]] = relationship("OutfitItem", back_populates="outfit", cascade="all, delete-orphan", lazy="selectin")


class OutfitItem(Base):
    __tablename__ = "outfit_item"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    outfit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("outfit.id", ondelete="CASCADE"))
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id", ondelete="CASCADE"))
    slot: Mapped[str] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="items")


class OutfitRevision(Base):
    __tablename__ = "outfit_revision"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    outfit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("outfit.id", ondelete="CASCADE"))
    rev_no: Mapped[int] = mapped_column(Integer, default=1)
    items_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attributes_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutfitWearLog(Base):
    __tablename__ = "outfit_wear_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    outfit_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("outfit.id", ondelete="CASCADE"))
    outfit_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("outfit_revision.id", ondelete="SET NULL"))
    worn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    worn_date: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    event: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    weather: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    season: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OutfitWearLogItem(Base):
    __tablename__ = "outfit_wear_log_item"
    wear_log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("outfit_wear_log.id", ondelete="CASCADE"), primary_key=True)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id", ondelete="CASCADE"), primary_key=True)
    slot: Mapped[str] = mapped_column(String(32))


class ItemWearLog(Base):
    __tablename__ = "item_wear_log"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("item.id", ondelete="CASCADE"))
    worn_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    worn_date: Mapped[date | None] = mapped_column(sa.Date(), nullable=True)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SuggestSession(Base):
    __tablename__ = "suggest_session"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    candidate_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cursor: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class User(Base):
    __tablename__ = "user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(Text, unique=True, nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "account"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(Text)
    provider_user_id: Mapped[str] = mapped_column(Text)
    raw_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class PasswordResetToken(Base):
    __tablename__ = "password_reset_token"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("user.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ItemSuggestionAudit(Base):
    __tablename__ = "item_suggestion_audit"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    image_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    hints: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_used: Mapped[bool] = mapped_column(Boolean, default=False)
    llm_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    family_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    family_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    type_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    type_top3: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    pattern_pred: Mapped[str | None] = mapped_column(Text, nullable=True)
    pattern_p: Mapped[float | None] = mapped_column(Float, nullable=True)
    pattern_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feature_wait_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feature_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    had_family_hint: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
