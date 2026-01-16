from uuid import UUID
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, date
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, insert, select, func
from sqlalchemy.orm import selectinload
from app.core.db import get_session
from app.core.config import settings
from app.auth.deps import get_current_user_id, get_user_id_optional
from app.core.tags import ALLOWED_EVENTS, ALLOWED_SEASONS, clamp_limits, normalize_many, normalize_tag
from app.core.taxonomy import get_taxonomy
from app.models.models import Item, ItemSuggestionAudit, ItemImage
from app.services.features import load_features
from app.services import llm as llm_service
from app.services.llm.types import SuggestItemAttributesInput
from app.storage.r2 import presign_put, object_url, presign_get, r2_client, R2_BUCKET
from app.storage.keys import original_key
from pydantic import BaseModel, field_validator
from botocore.exceptions import ClientError
from app.models.models import OutfitWearLog, OutfitWearLogItem, ItemWearLog
from workers.tasks import analyze_image
from app.schemas.schemas import (
    ItemCreate,
    ItemUpdate,
    ItemOut,
    ItemWearLogIn,
    ItemWearLogOut,
    ItemWearLogDeleteIn,
    SuggestAttributesIn,
    SuggestAttributesOut,
    SuggestDraft,
    SuggestField,
    TagPatch,
    ItemWearLogIn,
    ItemWearLogOut,
)

router = APIRouter(prefix="/items", tags=["items"])
# Use uvicorn logger so INFO messages show up in container logs
logger = logging.getLogger("uvicorn.error")

ATTRIBUTE_SOURCE_FIELDS = {
    "status": "status",
    "category": "category",
    "type": "item_type",
    "fit": "fit",
    "fabric_kind": "fabric_kind",
    "pattern": "pattern",
    "tone": "tone",
    "layer_role": "layer_role",
    "name": "name",
    "brand": "brand",
    "base_color": "base_color",
    "material": "material",
    "warmth": "warmth",
    "formality": "formality",
    "kind": "kind",
}
TAG_SOURCE_FIELDS = {
    "style_tags": "style_tags",
    "event_tags": "event_tags",
    "season_tags": "season_tags",
}

def _apply_updates(item: Item, data: Dict[str, Any], category_hint: Optional[str]) -> None:
    if "kind" in data and data["kind"]:
        item.kind = data["kind"]
    if "status" in data and data["status"]:
        item.status = data["status"]
    if "category" in data and data["category"]:
        item.category = _normalize_facet("category", data["category"])
    if "type" in data and data["type"]:
        item.item_type = _normalize_facet("type", data["type"], category=item.category or category_hint)
    if "fit" in data:
        item.fit = _normalize_facet("fit", data["fit"], category=item.category or category_hint)
    if "fabric_kind" in data:
        item.fabric_kind = _normalize_facet("fabric_kind", data["fabric_kind"])
    if "pattern" in data:
        item.pattern = _normalize_facet("pattern", data["pattern"])
    if "tone" in data:
        item.tone = _normalize_facet("tone", data["tone"])
    if "layer_role" in data:
        item.layer_role = _normalize_facet("layer_role", data["layer_role"])
    if "name" in data:
        item.name = data["name"]
    if "brand" in data:
        item.brand = data["brand"]
    if "base_color" in data:
        item.base_color = _normalize_facet("base_color", data["base_color"])
    if "material" in data:
        item.material = _normalize_facet("material", data["material"])
    if "warmth" in data:
        item.warmth = _normalize_facet("warmth", data["warmth"])
    if "formality" in data:
        item.formality = _normalize_facet("formality", data["formality"])

def _update_attribute_sources(
    item: Item,
    updates: Dict[str, Any],
    before: Dict[str, Any],
    field_map: Dict[str, str],
    source_overrides: Optional[Dict[str, str]] = None,
) -> None:
    sources = dict(item.attribute_sources or {})
    now = datetime.now(timezone.utc).isoformat()
    overrides = source_overrides or {}
    for api_field, model_field in field_map.items():
        if api_field not in updates:
            continue
        if before.get(model_field) == getattr(item, model_field):
            continue
        source = overrides.get(api_field, "user")
        sources[api_field] = {"source": source, "updated_at": now}
    if sources:
        item.attribute_sources = sources

def _tag_error(category: str, tag: str, reason: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": "invalid_tag", "details": {"category": category, "tag": tag, "reason": reason}},
    )

def _normalize_category_tags(category: str, values: Optional[List[str]]) -> list[str]:
    try:
        normalized = normalize_many(values or [])
    except ValueError as e:
        raise _tag_error(category, values[0] if values else "", str(e))
    if category == "season":
        for t in normalized:
            if t not in ALLOWED_SEASONS:
                raise _tag_error(category, t, "not_in_enum")
    if category == "event":
        for t in normalized:
            if t not in ALLOWED_EVENTS:
                raise _tag_error(category, t, "not_in_enum")
    max_len = {"style": 10, "event": 6, "season": 2}[category]
    if len(normalized) > max_len:
        raise _tag_error(category, normalized[max_len], "too_many_tags")
    # Clamp to enforce limits defensively
    st, ev, se = clamp_limits(
        normalized if category == "style" else [],
        normalized if category == "event" else [],
        normalized if category == "season" else [],
    )
    return {"style": st, "event": ev, "season": se}[category]

def _parse_query_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    return [x for x in raw.split(",") if x]

def _build_filter_conditions(
    style: Optional[str],
    event: Optional[str],
    season: Optional[str],
    any_style: Optional[str],
    any_event: Optional[str],
):
    style_list = _normalize_category_tags("style", _parse_query_list(style)) if style else []
    event_list = _normalize_category_tags("event", _parse_query_list(event)) if event else []
    season_list = _normalize_category_tags("season", _parse_query_list(season)) if season else []
    any_style_list = _normalize_category_tags("style", _parse_query_list(any_style)) if any_style else []
    any_event_list = _normalize_category_tags("event", _parse_query_list(any_event)) if any_event else []

    conds = []
    if style_list:
        conds.append(Item.style_tags.contains(style_list))
    if event_list:
        conds.append(Item.event_tags.contains(event_list))
    if season_list:
        conds.append(Item.season_tags.contains(season_list))
    if any_style_list:
        conds.append(Item.style_tags.overlap(any_style_list))
    if any_event_list:
        conds.append(Item.event_tags.overlap(any_event_list))

    return conds

def _normalize_facet(name: str, value: Optional[Any], category: Optional[str] = None) -> Optional[Any]:
    if value is None:
        return None
    taxonomy = get_taxonomy()["facets"]
    if name == "formality":
        try:
            v = float(value)
        except (TypeError, ValueError):
            raise _tag_error(name, str(value), "invalid_value")
        if v < 0 or v > 1:
            raise _tag_error(name, str(value), "invalid_value")
        return round(v, 2)
    if name == "warmth":
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise _tag_error(name, str(value), "invalid_value")
        if v not in taxonomy["warmth"]["values"]:
            raise _tag_error(name, str(value), "invalid_value")
        return v
    allowed = taxonomy.get(name, {}).get("values")
    if allowed is None:
        return normalize_tag(str(value))
    if isinstance(allowed, dict):
        if not category:
            raise _tag_error(name, str(value), "missing_category")
    if name == "type":
        if not category:
            raise _tag_error(name, str(value), "missing_category")
        allowed = taxonomy["type"]["values"].get(category, [])
    val = normalize_tag(str(value))
    if isinstance(allowed, dict):
        allowed_list = allowed.get(category or "", [])
    else:
        allowed_list = allowed
    if val not in allowed_list:
        raise _tag_error(name, val, "not_in_enum")
    return val

def _normalize_view(view: Optional[str]) -> str:
    v = (view or "front").lower()
    if v not in {"front", "back", "side"}:
        raise _tag_error("view", v, "not_in_enum")
    return v


def _image_url(img: ItemImage) -> str:
    if img.key:
        try:
            return presign_get(img.key, bucket=img.bucket or R2_BUCKET)
        except Exception:
            pass
    if img.url:
        return img.url
    if img.key:
        return object_url(img.key)
    return ""


def _compute_worn_times(worn_at_str: Optional[str]) -> tuple[datetime, datetime.date]:
    from zoneinfo import ZoneInfo

    tz_london = ZoneInfo("Europe/London")
    if worn_at_str:
        try:
            dt = datetime.fromisoformat(worn_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    worn_date = dt.astimezone(tz_london).date()
    return dt, worn_date


@router.get("/{item_id}/usage")
async def item_usage(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    # last worn and count from wear logs
    res = await session.execute(
        select(func.max(OutfitWearLog.worn_at), func.count(OutfitWearLog.id))
        .join(OutfitWearLogItem, OutfitWearLogItem.wear_log_id == OutfitWearLog.id)
        .where(
            OutfitWearLog.user_id == user_id,
            OutfitWearLogItem.item_id == item_id,
            OutfitWearLog.deleted_at.is_(None),
        )
    )
    last_worn_outfit, count_outfit = res.one()
    res = await session.execute(
        select(func.max(ItemWearLog.worn_at), func.count(ItemWearLog.id)).where(
            ItemWearLog.user_id == user_id,
            ItemWearLog.item_id == item_id,
            ItemWearLog.deleted_at.is_(None),
        )
    )
    last_worn_item, count_item = res.one()
    last_worn = max([dt for dt in [last_worn_outfit, last_worn_item] if dt is not None], default=None)
    return {
        "item_id": str(item_id),
        "last_worn_at": str(last_worn) if last_worn else None,
        "wear_count": int((count_outfit or 0) + (count_item or 0)),
    }


@router.post("/{item_id}/wear-log", response_model=ItemWearLogOut)
async def log_item_wear(
    item_id: UUID,
    payload: ItemWearLogIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item or str(item.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="item_not_found")
    worn_at, worn_date = _compute_worn_times(payload.worn_at)

    # idempotent per day
    res = await session.execute(
        select(ItemWearLog).where(
            ItemWearLog.user_id == user_id,
            ItemWearLog.item_id == item_id,
            ItemWearLog.worn_date == worn_date,
            ItemWearLog.deleted_at.is_(None),
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        return ItemWearLogOut(
            id=str(existing.id),
            item_id=str(existing.item_id),
            worn_at=str(existing.worn_at),
            worn_date=str(existing.worn_date),
            source=existing.source,
        )

    log = ItemWearLog(
        user_id=user_id,
        item_id=item_id,
        worn_at=worn_at,
        worn_date=worn_date,
        source=payload.source or "quick_log",
    )
    session.add(log)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        # race: try fetch existing
        res = await session.execute(
            select(ItemWearLog).where(
                ItemWearLog.user_id == user_id,
                ItemWearLog.item_id == item_id,
                ItemWearLog.worn_date == worn_date,
                ItemWearLog.deleted_at.is_(None),
            )
        )
        existing = res.scalar_one_or_none()
        if existing:
            return ItemWearLogOut(
                id=str(existing.id),
                item_id=str(existing.item_id),
                worn_at=str(existing.worn_at),
                worn_date=str(existing.worn_date),
                source=existing.source,
            )
        raise
    await session.refresh(log)
    return ItemWearLogOut(
        id=str(log.id),
        item_id=str(log.item_id),
        worn_at=str(log.worn_at),
        worn_date=str(log.worn_date),
        source=log.source,
    )


@router.patch("/{item_id}/wear-log/{log_id}", status_code=204)
async def delete_item_wear_log(
    item_id: UUID,
    log_id: UUID,
    payload: ItemWearLogDeleteIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    data = payload.model_dump(exclude_unset=True)
    if data.get("deleted") is not True and data.get("source") != "deleted":
        raise HTTPException(status_code=400, detail="invalid_delete_request")
    res = await session.execute(
        select(ItemWearLog).where(
            ItemWearLog.id == log_id,
            ItemWearLog.item_id == item_id,
            ItemWearLog.user_id == user_id,
        )
    )
    log = res.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="wear_log_not_found")
    if log.deleted_at is None:
        log.deleted_at = datetime.now(timezone.utc)
        if data.get("source"):
            log.source = data["source"]
        elif data.get("deleted") is True and not log.source:
            log.source = "deleted"
        await session.commit()
    return None


@router.get("/{item_id}/history", response_model=list[ItemWearLogOut])
async def item_history(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item or str(item.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="item_not_found")
    res = await session.execute(
        select(ItemWearLog)
        .where(
            ItemWearLog.user_id == user_id,
            ItemWearLog.item_id == item_id,
            ItemWearLog.deleted_at.is_(None),
        )
        .order_by(ItemWearLog.worn_at.desc())
    )
    logs = res.scalars().all()
    return [
        ItemWearLogOut(
            id=str(l.id),
            item_id=str(l.item_id),
            worn_at=str(l.worn_at),
            worn_date=str(getattr(l, "worn_date", None)) if getattr(l, "worn_date", None) else None,
            source=l.source,
        )
        for l in logs
    ]


ALLOWED_CT = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class PresignIn(BaseModel):
    content_type: str
    view: str

    @field_validator("content_type")
    @classmethod
    def _ct(cls, v: str):
        if v not in ALLOWED_CT:
            raise ValueError("unsupported_content_type")
        return v

    @field_validator("view")
    @classmethod
    def _view(cls, v: str):
        vv = v.lower()
        if vv not in {"front", "back", "side"}:
            raise ValueError("invalid_view")
        return vv


class PresignOut(BaseModel):
    key: str
    upload_url: str
    headers: Dict[str, str]
    cdn_url: Optional[str] = None


@router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: UUID,
    payload: ItemUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")

    data = payload.model_dump(exclude_unset=True)
    source_overrides = data.pop("attribute_sources", None) or {}
    before = {model_field: getattr(item, model_field) for model_field in ATTRIBUTE_SOURCE_FIELDS.values()}
    # normalize and apply
    category_hint = data.get("category") or item.category
    _apply_updates(item, data, category_hint)
    _update_attribute_sources(item, data, before, ATTRIBUTE_SOURCE_FIELDS, source_overrides)

    await session.commit()
    await session.refresh(item)
    return _build_item_out(item)


@router.delete("/{item_id}", status_code=204)
async def delete_item(
    item_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    await session.delete(item)
    await session.commit()
    return None


@router.get("/facets")
async def item_facets(
    style: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    any_style: Optional[str] = Query(None, alias="any_style"),
    any_event: Optional[str] = Query(None, alias="any_event"),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    conds = _build_filter_conditions(style, event, season, any_style, any_event)
    base = select(Item).where(Item.user_id == user_id)
    if conds:
        base = base.where(and_(*conds))
    cte = base.cte("filtered")

    results: dict[str, dict[str, int]] = {"type": {}, "event": {}, "season": {}, "base_color": {}}

    # type counts
    type_q = select(cte.c.item_type, func.count().label("cnt")).where(cte.c.item_type.isnot(None)).group_by(cte.c.item_type)
    for row in (await session.execute(type_q)).all():
        results["type"][row[0]] = row[1]

    # base_color counts
    color_q = (
        select(cte.c.base_color, func.count().label("cnt"))
        .where(cte.c.base_color.isnot(None))
        .group_by(cte.c.base_color)
    )
    for row in (await session.execute(color_q)).all():
        results["base_color"][row[0]] = row[1]

    # event_tags counts
    event_q = select(func.unnest(cte.c.event_tags).label("val"), func.count().label("cnt")).group_by("val")
    for row in (await session.execute(event_q)).all():
        if row[0] is not None:
            results["event"][row[0]] = row[1]

    # season_tags counts
    season_q = select(func.unnest(cte.c.season_tags).label("val"), func.count().label("cnt")).group_by("val")
    for row in (await session.execute(season_q)).all():
        if row[0] is not None:
            results["season"][row[0]] = row[1]

    return results

def _build_item_out(item: Item) -> ItemOut:
    images = [
        {
            "id": str(img.id),
            "url": _image_url(img),
            "view": img.view or "front",
            "bg_removed": bool(img.bg_removed),
            "bucket": img.bucket,
            "key": img.key,
            "kind": img.kind,
            "bytes": img.bytes,
        }
        for img in getattr(item, "images", [])  # may be lazy-loaded if relationship added later
    ]
    return ItemOut(
        id=str(item.id),
        kind=item.kind,
        status=item.status,
        attribute_sources=item.attribute_sources,
        category=item.category,
        type=item.item_type,
        fit=item.fit,
        fabric_kind=item.fabric_kind,
        pattern=item.pattern,
        tone=item.tone,
        layer_role=item.layer_role,
        name=item.name,
        brand=item.brand,
        base_color=item.base_color,
        warmth=item.warmth,
        formality=item.formality,
        style_tags=item.style_tags or [],
        event_tags=item.event_tags or [],
        season_tags=item.season_tags or [],
        images=images,
    )

@router.post("", response_model=ItemOut)
async def create_item(
    payload: ItemCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    category = _normalize_facet("category", payload.category or payload.kind)
    item_type = _normalize_facet("type", payload.type, category=category) if payload.type else None
    fit = _normalize_facet("fit", payload.fit, category=category) if payload.fit else None
    fabric_kind = _normalize_facet("fabric_kind", payload.fabric_kind) if payload.fabric_kind else None
    pattern = _normalize_facet("pattern", payload.pattern) if payload.pattern else None
    tone = _normalize_facet("tone", payload.tone) if payload.tone else None
    layer_role = _normalize_facet("layer_role", payload.layer_role) if payload.layer_role else None
    base_color = _normalize_facet("base_color", payload.base_color) if payload.base_color else None
    material = _normalize_facet("material", payload.material) if payload.material else None
    warmth = _normalize_facet("warmth", payload.warmth) if payload.warmth is not None else None
    formality = _normalize_facet("formality", payload.formality) if payload.formality is not None else None
    style_tags = _normalize_category_tags("style", payload.style_tags)
    event_tags = _normalize_category_tags("event", payload.event_tags)
    season_tags = _normalize_category_tags("season", payload.season_tags)
    data = payload.model_dump()
    source_overrides = data.pop("attribute_sources", None) or {}
    # Remove alias-only field; we store it as item_type
    data.pop("type", None)
    # Images are stored in item_image table, not on item
    images_payload = data.pop("images", None)
    data.update(
        {
            "category": category,
            "item_type": item_type,
            "fit": fit,
            "fabric_kind": fabric_kind,
            "pattern": pattern,
            "tone": tone,
            "layer_role": layer_role,
            "base_color": base_color,
            "material": material,
            "warmth": warmth,
            "formality": formality,
            "kind": category or payload.kind,
        }
    )
    data.update(
        {
            "style_tags": style_tags if payload.style_tags is not None else None,
            "event_tags": event_tags if payload.event_tags is not None else None,
            "season_tags": season_tags if payload.season_tags is not None else None,
        }
    )
    sources: dict[str, dict[str, str]] = {}
    now = datetime.now(timezone.utc).isoformat()
    for api_field, model_field in ATTRIBUTE_SOURCE_FIELDS.items():
        value = data.get(model_field)
        if api_field == "type":
            value = item_type
        if value is None:
            continue
        sources[api_field] = {"source": source_overrides.get(api_field, "user"), "updated_at": now}
    for api_field, model_field in TAG_SOURCE_FIELDS.items():
        value = data.get(model_field)
        if value is None:
            continue
        sources[api_field] = {"source": source_overrides.get(api_field, "user"), "updated_at": now}
    if sources:
        data["attribute_sources"] = sources
    stmt = insert(Item).values(**data, user_id=user_id).returning(Item)
    res = await session.execute(stmt)
    item = res.scalar_one()

    # Images
    image_payloads = images_payload or []
    for img in image_payloads:
        view = _normalize_view(img.get("view") if isinstance(img, dict) else getattr(img, "view", None))
        url = img.get("url") if isinstance(img, dict) else getattr(img, "url", None)
        session.add(
            ItemImage(
                item_id=item.id,
                url=url,
                view=view,
                bg_removed=False,
            )
        )
    await session.commit()
    await session.refresh(item)
    return _build_item_out(item)

@router.get("", response_model=list[ItemOut])
async def list_items(
    style: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    any_style: Optional[str] = Query(None, alias="any_style"),
    any_event: Optional[str] = Query(None, alias="any_event"),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    conds = _build_filter_conditions(style, event, season, any_style, any_event)
    q = select(Item).options(selectinload(Item.images)).where(Item.user_id == user_id).order_by(Item.created_at.desc())
    if conds:
        q = q.where(and_(*conds))
    res = await session.execute(q)
    return [_build_item_out(i) for i in res.scalars().all()]

@router.patch("/{item_id}/tags")
async def patch_item_tags(
    item_id: UUID,
    payload: TagPatch,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")

    normalized_style = _normalize_category_tags("style", payload.style_tags)
    normalized_event = _normalize_category_tags("event", payload.event_tags)
    normalized_season = _normalize_category_tags("season", payload.season_tags)

    style_existing = item.style_tags or []
    event_existing = item.event_tags or []
    season_existing = item.season_tags or []

    def apply_op(existing: list[str], incoming: list[str], category: str, limit: int) -> list[str]:
        if payload.op == "set":
            new_vals = incoming if payload.__fields_set__.intersection({f"{category}_tags"}) else existing
        elif payload.op == "add":
            new_vals = existing + [x for x in incoming if x not in existing]
        elif payload.op == "remove":
            new_vals = [x for x in existing if x not in incoming]
        else:
            new_vals = existing
        if len(new_vals) > limit:
            raise _tag_error(category, new_vals[limit], "too_many_tags")
        return new_vals

    style_tags = apply_op(style_existing, normalized_style, "style", 10)
    event_tags = apply_op(event_existing, normalized_event, "event", 6)
    season_tags = apply_op(season_existing, normalized_season, "season", 2)

    # Final clamp to enforce allowed seasons and lengths
    style_tags, event_tags, season_tags = clamp_limits(style_tags, event_tags, season_tags)

    item.style_tags = style_tags
    item.event_tags = event_tags
    item.season_tags = season_tags
    updates: Dict[str, Any] = {}
    if style_tags != style_existing:
        updates["style_tags"] = style_tags
    if event_tags != event_existing:
        updates["event_tags"] = event_tags
    if season_tags != season_existing:
        updates["season_tags"] = season_tags
    if updates:
        before = {
            "style_tags": style_existing,
            "event_tags": event_existing,
            "season_tags": season_existing,
        }
        _update_attribute_sources(item, updates, before, TAG_SOURCE_FIELDS)
    await session.commit()
    await session.refresh(item)

    return {
        "id": str(item.id),
        "style_tags": item.style_tags or [],
        "event_tags": item.event_tags or [],
        "season_tags": item.season_tags or [],
    }

@router.post("/{item_id}/images")
async def add_item_images(
    item_id: UUID,
    images: List[Dict[str, Any]],
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    created = []
    for img in images:
        url = img.get("url")
        if not url:
            raise HTTPException(status_code=400, detail="image_url_required")
        view = _normalize_view(img.get("view"))
        new_img = ItemImage(item_id=item_id, user_id=user_id, url=url, view=view, bg_removed=False)
        session.add(new_img)
        created.append(new_img)
    await session.commit()
    for c in created:
        await session.refresh(c)
    return [
        {"id": str(c.id), "url": c.url, "view": c.view, "bg_removed": bool(c.bg_removed)}
        for c in created
    ]


def _ext_from_content_type(ct: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }.get(ct, "jpg")


@router.post("/{item_id}/images/presign", response_model=PresignOut)
async def presign_image(
    item_id: UUID, body: PresignIn, session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id)
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    ext = _ext_from_content_type(body.content_type)
    key = original_key(str(user_id), str(item_id), ext)
    upload_url, headers = presign_put(key, body.content_type)
    return PresignOut(key=key, upload_url=upload_url, headers=headers, cdn_url=object_url(key))


class ConfirmIn(BaseModel):
    key: str
    view: str = "front"

    @field_validator("view")
    @classmethod
    def _view(cls, v: str):
        vv = v.lower()
        if vv not in {"front", "back", "side"}:
            raise ValueError("invalid_view")
        return vv


@router.post("/{item_id}/images/confirm")
async def confirm_image(
    item_id: UUID, body: ConfirmIn, session: AsyncSession = Depends(get_session), user_id: str = Depends(get_current_user_id)
):
    item = await session.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.user_id and str(item.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="forbidden")
    s3 = r2_client()
    try:
        head = s3.head_object(Bucket=R2_BUCKET, Key=body.key)
    except ClientError as e:
        raise HTTPException(status_code=400, detail="object_not_found") from e
    bytes_ = int(head.get("ContentLength") or 0)
    url = object_url(body.key)
    img = ItemImage(
        item_id=item_id,
        user_id=user_id,
        bucket=R2_BUCKET,
        key=body.key,
        url=url,
        view=body.view,
        kind="original",
        bytes=bytes_,
        bg_removed=False,
    )
    session.add(img)
    await session.commit()
    await session.refresh(img)
    try:
        analyze_image.delay(str(img.id))
    except Exception:
        pass
    return {"id": str(img.id), "url": img.url, "view": img.view, "key": img.key, "bucket": img.bucket}

def _default_draft(hints: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    # Category/family
    category = hints.get("category") or features.get("category") or (features.get("clip_family") if (features.get("clip_family_p") or 0) >= 0.5 else None)
    base_color = hints.get("base_color") or features.get("base_color") or None
    # Type: prefer hint, then clip with confidence gate, then heuristics
    type_guess = hints.get("type") or (
        features.get("clip_type") if (features.get("clip_type_p") or 0) >= settings.SUGGEST_TYPE_MIN_P else None
    ) or features.get("type") or None
    tone = hints.get("tone") or features.get("tone") or ("cool" if base_color in {"navy", "blue", "black", "gray"} else "warm")
    # Pattern: heuristics first, then clip
    pattern_guess = hints.get("pattern") or features.get("pattern")
    if not pattern_guess and (features.get("clip_pattern_p") or 0) >= settings.SUGGEST_PATTERN_MIN_P:
        pattern_guess = features.get("clip_pattern")
    base_conf = 0.9 if features.get("base_color") else (0.9 if "base_color" in hints else 0.0)
    tone_conf = 0.8 if features.get("tone") else 0.6
    pattern_conf = features.get("pattern_confidence", 0.0)
    if pattern_guess == features.get("clip_pattern"):
        pattern_conf = max(pattern_conf, features.get("clip_pattern_p") or 0.0)
    formality_guess = hints.get("formality") or features.get("formality") or 0.5
    warmth_guess = hints.get("warmth") or features.get("warmth") or 0
    layer_guess = hints.get("layer_role") or ("outer" if warmth_guess >= 2 else "base")
    reasons = {
        "base_color": features.get("reason") or "dominant color heuristic",
        "tone": "derived from hue/sat",
        "pattern": "contrast heuristic" if features.get("pattern") else "unsure",
        "formality": "priors from type/pattern/color",
    }
    cat_source = "hint" if hints.get("category") else ("vision" if features.get("category") else "clip" if features.get("clip_family") else "rule")
    type_source = (
        "hint"
        if hints.get("type")
        else ("clip" if type_guess == features.get("clip_type") else "vision" if features.get("type") else "rule")
    )
    pattern_source = (
        "hint"
        if hints.get("pattern")
        else ("clip" if pattern_guess == features.get("clip_pattern") else "vision" if features.get("pattern") else "rule")
    )

    draft: Dict[str, Dict[str, Any]] = {
        "category": {"value": category, "confidence": 0.9 if "category" in hints else (0.7 if category else 0.0), "source": cat_source},
        "type": {"value": type_guess, "confidence": max(0.65 if type_guess else 0.0, features.get("clip_type_p") or 0.0), "source": type_source},
        "base_color": {"value": base_color, "confidence": base_conf, "source": "color" if features.get("base_color") else "hint" if hints.get("base_color") else "rule", "reason": reasons["base_color"]},
        "tone": {"value": tone, "confidence": tone_conf, "source": "rule", "reason": reasons["tone"]},
        "warmth": {"value": warmth_guess, "confidence": 0.6, "source": "rule"},
        "formality": {"value": formality_guess, "confidence": 0.65, "source": "rule", "reason": reasons["formality"]},
        "layer_role": {"value": layer_guess, "confidence": 0.7, "source": "rule"},
        "pattern": {"value": pattern_guess, "confidence": max(pattern_conf, features.get("clip_pattern_p") or 0.0), "source": pattern_source, "reason": reasons["pattern"]},
        "fabric_kind": {"value": "woven", "confidence": 0.6, "source": "vision"},
        "material": {"value": "cotton", "confidence": 0.5, "source": "llm"},
        "season_tags": {"value": ["spring", "autumn"], "confidence": 0.5, "source": "llm"},
        "event_tags": {"value": ["casual"], "confidence": 0.5, "source": "llm"},
        "style_tags": {"value": ["minimal"], "confidence": 0.5, "source": "llm"},
    }
    return draft

def _apply_locks(draft: Dict[str, Dict[str, Any]], lock_fields: set[str], hints: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    data = {k: v.copy() for k, v in draft.items()}
    for field in lock_fields:
        if field in data:
            value = hints.get(field, data[field].get("value"))
            data[field] = {"value": value, "confidence": 0.99, "source": "locked", "reason": "client-locked"}
    return data


def _apply_thresholds(draft: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Clear low-confidence guesses based on configured gates."""
    data = {k: v.copy() for k, v in draft.items()}
    type_field = data.get("type")
    if type_field and (type_field.get("confidence") or 0) < settings.SUGGEST_TYPE_MIN_P:
        data["type"] = {"value": None, "confidence": 0.0, "source": "rule", "reason": "below_type_threshold"}
    pattern_field = data.get("pattern")
    if pattern_field and (pattern_field.get("confidence") or 0) < settings.SUGGEST_PATTERN_MIN_P:
        data["pattern"] = {"value": None, "confidence": 0.0, "source": "rule", "reason": "below_pattern_threshold"}
    return data

def _normalize_suggest_field(
    name: str, field: Optional[Dict[str, Any]], category: Optional[str]
) -> Optional[Dict[str, Any]]:
    if field is None:
        return None
    val = field.get("value")
    try:
        normalized = _normalize_facet(name if name != "type" else "type", val, category=category)
    except HTTPException:
        normalized = None
        field["confidence"] = 0.3
    field["value"] = normalized
    return field


def _normalize_draft_fields(draft_data: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Normalize draft values against taxonomy and clamp tag sets."""
    category_val = draft_data.get("category", {}).get("value")
    draft_data["category"] = _normalize_suggest_field("category", draft_data.get("category"), category_val)
    draft_data["type"] = _normalize_suggest_field("type", draft_data.get("type"), category_val)
    draft_data["base_color"] = _normalize_suggest_field("base_color", draft_data.get("base_color"), category_val)
    draft_data["tone"] = _normalize_suggest_field("tone", draft_data.get("tone"), category_val)
    draft_data["layer_role"] = _normalize_suggest_field("layer_role", draft_data.get("layer_role"), category_val)
    draft_data["pattern"] = _normalize_suggest_field("pattern", draft_data.get("pattern"), category_val)
    draft_data["fabric_kind"] = _normalize_suggest_field("fabric_kind", draft_data.get("fabric_kind"), category_val)
    draft_data["material"] = _normalize_suggest_field("material", draft_data.get("material"), category_val)
    draft_data["warmth"] = _normalize_suggest_field("warmth", draft_data.get("warmth"), category_val)
    draft_data["formality"] = _normalize_suggest_field("formality", draft_data.get("formality"), category_val)

    # Normalize tag sets
    if draft_data.get("season_tags"):
        try:
            draft_data["season_tags"]["value"] = _normalize_category_tags("season", draft_data["season_tags"]["value"])
        except HTTPException:
            draft_data["season_tags"]["value"] = []
            draft_data["season_tags"]["confidence"] = 0.3
    if draft_data.get("event_tags"):
        try:
            draft_data["event_tags"]["value"] = _normalize_category_tags("event", draft_data["event_tags"]["value"])
        except HTTPException:
            draft_data["event_tags"]["value"] = []
            draft_data["event_tags"]["confidence"] = 0.3
    if draft_data.get("style_tags"):
        try:
            draft_data["style_tags"]["value"] = _normalize_category_tags("style", draft_data["style_tags"]["value"])
        except HTTPException:
            draft_data["style_tags"]["value"] = []
            draft_data["style_tags"]["confidence"] = 0.3

    return draft_data


def _merge_llm_suggestions(
    draft_data: Dict[str, Dict[str, Any]], suggestions: Dict[str, Any], lock_fields: set[str]
) -> Dict[str, Dict[str, Any]]:
    merged = {k: (v.copy() if isinstance(v, dict) else v) for k, v in draft_data.items()}
    min_conf = settings.LLM_ATTR_MIN_CONFIDENCE
    for field, sugg in (suggestions or {}).items():
        if field in lock_fields:
            continue
        if not isinstance(sugg, dict):
            try:
                sugg = sugg.model_dump()
            except Exception:
                continue
        val = sugg.get("value")
        conf = float(sugg.get("confidence") or 0.0)
        rationale = sugg.get("rationale") or sugg.get("reason")
        if val is None or conf < min_conf:
            continue
        merged[field] = {"value": val, "confidence": conf, "source": "llm", "reason": rationale}
    return merged

@router.post("/suggest-attributes", response_model=SuggestAttributesOut)
async def suggest_attributes(
    payload: SuggestAttributesIn, session: AsyncSession = Depends(get_session), user_id: str = Depends(get_user_id_optional)
):
    started = time.time()
    hints = payload.hints or {}
    lock_fields = set(payload.lock_fields or [])

    features, pending_features = await load_features(
        payload.image_url,
        payload.image_b64,
        image_urls=payload.image_urls,
        image_b64s=payload.image_b64s,
        item_id=payload.item_id,
        image_ids=payload.image_ids,
        session=session,
        wait_ms=settings.LLM_SUGGEST_TIMEOUT_MS,
    )
    if features.get("ok"):
        logger.warning(
            "suggest-attributes: image features extracted source=%s url=%s b64=%s category=%s type=%s base_color=%s tone=%s pattern=%s clip_family=%s clip_type=%s clip_type_p=%s clip_pattern=%s clip_pattern_p=%s reason=%s dims=%s version=%s latency_ms=%s pending=%s",
            features.get("feature_source"),
            payload.image_url,
            bool(payload.image_b64),
            features.get("category"),
            features.get("type"),
            features.get("base_color"),
            features.get("tone"),
            features.get("pattern"),
            features.get("clip_family"),
            features.get("clip_type"),
            features.get("clip_type_p"),
            features.get("clip_pattern"),
            features.get("clip_pattern_p"),
            features.get("reason"),
            features.get("debug_dims"),
            features.get("features_version"),
            features.get("latency_ms"),
            pending_features,
        )
    else:
        logger.warning(
            "suggest-attributes: image features unavailable source=%s url=%s b64=%s b64_len=%s reason=%s pending=%s",
            features.get("feature_source"),
            payload.image_url,
            bool(payload.image_b64),
            len(payload.image_b64 or ""),
            features.get("reason"),
            pending_features,
        )
    draft_data = _default_draft(hints, features if features.get("ok") else {})
    draft_data = _apply_thresholds(draft_data)
    draft_data = _apply_locks(draft_data, lock_fields, hints)
    draft_data = _normalize_draft_fields(draft_data)

    # Optional LLM enrichment
    llm_meta = {}
    if settings.LLM_ENABLED:
        llm_payload = SuggestItemAttributesInput(
            taxonomy=get_taxonomy()["facets"],
            features=features if features.get("ok") else {},
            current=hints,
            locked=list(lock_fields),
            allow_vision=bool(payload.use_vision and settings.LLM_USE_VISION),
            image_url=payload.image_url if (payload.use_vision and settings.LLM_USE_VISION) else None,
            prompt_version="p1",
        )
        try:
            llm_out = await llm_service.suggest_item_attributes(llm_payload)
            llm_meta = llm_out.usage.model_dump()
            draft_data = _merge_llm_suggestions(draft_data, llm_out.suggestions, lock_fields)
            draft_data = _normalize_draft_fields(draft_data)
        except Exception as e:
            logger.warning("suggest-attributes: llm enrichment failed reason=%s", e)

    merged = SuggestDraft(**{k: v for k, v in draft_data.items() if v is not None})

    latency_ms = int((time.time() - started) * 1000)
    audit = ItemSuggestionAudit(
        image_ref=payload.image_url,
        hints=hints,
        draft=merged.model_dump(by_alias=True),
        latency_ms=latency_ms,
        llm_used=True if llm_meta else False,
        llm_tokens=llm_meta.get("tokens_out") if llm_meta else 0,
        provider=llm_meta.get("model") if llm_meta else None,
        user_id=user_id,
    )
    session.add(audit)
    await session.commit()

    return SuggestAttributesOut(draft=merged, pending_features=pending_features)
