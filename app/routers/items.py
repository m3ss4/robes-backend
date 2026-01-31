from uuid import UUID
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo
import asyncio
import time
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, insert, select, func, text
from sqlalchemy.orm import selectinload
from app.core.db import get_session
from app.core.config import settings
from app.auth.deps import get_current_user_id, get_user_id_optional
from app.routers.items_helpers import (
    ATTRIBUTE_SOURCE_FIELDS,
    TAG_SOURCE_FIELDS,
    PAIRING_CATEGORIES,
    TYPE_TO_CATEGORY,
    MAX_PAIRING_LIMIT,
    _apply_updates,
    _update_attribute_sources,
    _pairing_key_for_category,
    _normalize_pairing_list,
    _upsert_pairing_entry,
    _build_item_attributes,
    _build_attribute_sources,
    _tag_error,
    _normalize_category_tags,
    _parse_query_list,
    _build_filter_conditions,
    _normalize_facet,
    _normalize_view,
    _image_url,
    _compute_worn_times,
    _build_item_out,
    _ext_from_content_type,
    _default_draft,
    _apply_locks,
    _apply_thresholds,
    _normalize_suggest_field,
    _normalize_draft_fields,
    _merge_llm_suggestions,
)
from app.models.models import Item, ItemSuggestionAudit, ItemImage
from app.services.features import load_features
from app.services import llm as llm_service
from app.services.suggest import suggest_with_provider
from app.llm.types import SuggestAmbiguity
from app.services.llm.types import PairingCandidate, SuggestItemPairingsInput
from app.storage.r2 import presign_put, object_url, presign_get, r2_client, R2_BUCKET, R2_CDN_BASE
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
    ItemPairingRequest,
    ItemPairingResponse,
    ItemPairingSuggestion,
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


def _public_image_url(key: str, bucket: str | None) -> str:
    if R2_CDN_BASE:
        return f"{R2_CDN_BASE}/{key}"
    return presign_get(key, bucket=bucket)


async def _remove_item_from_all_pairings(session: AsyncSession, user_id: str, item_id: str) -> None:
    res = await session.execute(select(Item).where(Item.user_id == user_id, Item.id != item_id))
    items = res.scalars().all()
    for other in items:
        data = other.pairing_suggestions or {}
        if not data:
            continue
        changed = False
        for key in ("top", "bottom"):
            if key not in data:
                continue
            before = data.get(key) or []
            after = [entry for entry in before if entry.get("item_id") != item_id]
            if len(after) != len(before):
                data[key] = after
                changed = True
        if changed:
            other.pairing_suggestions = data


async def _acquire_pairing_lock(session: AsyncSession, item_id: UUID) -> None:
    lock_id = int.from_bytes(item_id.bytes, "big") % (2**63 - 1)
    await session.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": lock_id})


async def _compute_pairings_for_item(
    session: AsyncSession,
    item: Item,
    *,
    limit: int,
) -> list[dict]:
    if item.category not in PAIRING_CATEGORIES:
        return []
    target_category = _pairing_key_for_category(item.category)
    res = await session.execute(
        select(Item).where(
            Item.user_id == item.user_id,
            Item.category == target_category,
            Item.status == "active",
            Item.id != item.id,
        )
    )
    candidates = res.scalars().all()
    if not candidates:
        item.pairing_suggestions = {target_category: []}
        return []
    llm_payload = SuggestItemPairingsInput(
        base_item={
            "item_id": str(item.id),
            "attributes": _build_item_attributes(item),
            "attribute_sources": _build_attribute_sources(item),
        },
        candidates=[
            PairingCandidate(
                item_id=str(c.id),
                attributes=_build_item_attributes(c),
                attribute_sources=_build_attribute_sources(c),
            )
            for c in candidates
        ],
        limit=limit,
    )
    llm_out = await llm_service.suggest_item_pairings(llm_payload)
    candidate_map = {str(c.id): c for c in candidates}
    suggestions = []
    for s in llm_out.suggestions:
        if s.item_id not in candidate_map:
            continue
        suggestions.append({"item_id": s.item_id, "score": max(0.0, min(float(s.score), 100.0))})
    suggestions = _normalize_pairing_list(suggestions)
    item.pairing_suggestions = {target_category: suggestions}
    await _remove_item_from_all_pairings(session, str(item.user_id), str(item.id))
    for entry in suggestions:
        other = candidate_map.get(entry["item_id"])
        if not other:
            continue
        data = other.pairing_suggestions or {}
        existing = data.get(item.category, [])
        data[item.category] = _upsert_pairing_entry(existing, str(item.id), entry["score"])
        other.pairing_suggestions = data
    return suggestions


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


@router.post("/{item_id}/pairings", response_model=ItemPairingResponse)
async def item_pairings(
    item_id: UUID,
    payload: ItemPairingRequest,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    item = await session.get(Item, item_id)
    if not item or str(item.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="item_not_found")
    if item.category not in PAIRING_CATEGORIES:
        raise HTTPException(status_code=400, detail="pairing_not_supported")
    limit = max(1, min(int(payload.limit or 10), MAX_PAIRING_LIMIT))
    target_category = _pairing_key_for_category(item.category)
    cached_list = (item.pairing_suggestions or {}).get(target_category)
    if cached_list is not None:
        cached = _normalize_pairing_list(cached_list)
        return ItemPairingResponse(
            item_id=str(item.id),
            category=item.category,
            cached=True,
            suggestions=[ItemPairingSuggestion(**s) for s in cached[:limit]],
        )

    await _acquire_pairing_lock(session, item.id)
    refreshed = await session.get(Item, item_id)
    if refreshed:
        item = refreshed
    cached_list = (item.pairing_suggestions or {}).get(target_category)
    if cached_list is not None:
        cached = _normalize_pairing_list(cached_list)
        return ItemPairingResponse(
            item_id=str(item.id),
            category=item.category,
            cached=True,
            suggestions=[ItemPairingSuggestion(**s) for s in cached[:limit]],
        )

    try:
        suggestions = await _compute_pairings_for_item(session, item, limit=limit)
    except asyncio.TimeoutError:
        cached_list = (item.pairing_suggestions or {}).get(target_category)
        if cached_list is not None:
            cached = _normalize_pairing_list(cached_list)
            return ItemPairingResponse(
                item_id=str(item.id),
                category=item.category,
                cached=True,
                suggestions=[ItemPairingSuggestion(**s) for s in cached[:limit]],
            )
        raise HTTPException(status_code=504, detail="llm_timeout")
    await session.commit()
    return ItemPairingResponse(
        item_id=str(item.id),
        category=item.category,
        cached=False,
        suggestions=[ItemPairingSuggestion(**s) for s in suggestions[:limit]],
    )


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
    worn_at, worn_date = _compute_worn_times(payload.worn_at, payload.worn_date)
    today = datetime.now(ZoneInfo("Europe/London")).date()
    is_future = worn_date > today

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
            is_future=is_future,
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
                is_future=is_future,
            )
        raise
    await session.refresh(log)
    return ItemWearLogOut(
        id=str(log.id),
        item_id=str(log.item_id),
        worn_at=str(log.worn_at),
        worn_date=str(log.worn_date),
        source=log.source,
        is_future=is_future,
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
        today = datetime.now(ZoneInfo("Europe/London")).date()
        if log.source_outfit_log_id and log.worn_date == today:
            res = await session.execute(
                select(OutfitWearLog).where(
                    OutfitWearLog.id == log.source_outfit_log_id,
                    OutfitWearLog.user_id == user_id,
                    OutfitWearLog.deleted_at.is_(None),
                )
            )
            outfit_log = res.scalar_one_or_none()
            if outfit_log:
                outfit_log.deleted_at = datetime.now(timezone.utc)
                if not outfit_log.source:
                    outfit_log.source = "auto_reset"
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
            is_future=(l.worn_date > datetime.now(ZoneInfo("Europe/London")).date()) if l.worn_date else None,
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
    attributes_changed = any(before[field] != getattr(item, field) for field in ATTRIBUTE_SOURCE_FIELDS.values())
    was_pairable = before.get("category") in PAIRING_CATEGORIES
    now_pairable = item.category in PAIRING_CATEGORIES
    if attributes_changed and (was_pairable or now_pairable):
        item.pairing_suggestions = None
        if now_pairable and settings.LLM_ENABLED:
            await _acquire_pairing_lock(session, item.id)
            try:
                await _compute_pairings_for_item(session, item, limit=MAX_PAIRING_LIMIT)
            except asyncio.TimeoutError:
                logger.warning("pairings: llm timeout item_id=%s", item.id)
        else:
            await _remove_item_from_all_pairings(session, str(user_id), str(item.id))

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
    await _remove_item_from_all_pairings(session, str(user_id), str(item.id))
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
        if item.category in PAIRING_CATEGORIES:
            item.pairing_suggestions = None
            if settings.LLM_ENABLED:
                await _acquire_pairing_lock(session, item.id)
                try:
                    await _compute_pairings_for_item(session, item, limit=MAX_PAIRING_LIMIT)
                except asyncio.TimeoutError:
                    logger.warning("pairings: llm timeout item_id=%s", item.id)
            else:
                await _remove_item_from_all_pairings(session, str(user_id), str(item.id))
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
    return PresignOut(key=key, upload_url=upload_url, headers=headers, cdn_url=_public_image_url(key, R2_BUCKET))


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
    url = _public_image_url(body.key, R2_BUCKET)
    img = ItemImage(
        item_id=item_id,
        user_id=user_id,
        bucket=R2_BUCKET,
        key=body.key,
        url=url if R2_CDN_BASE else None,
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
    public_url = img.url or _public_image_url(img.key, img.bucket)
    return {"id": str(img.id), "url": public_url, "view": img.view, "key": img.key, "bucket": img.bucket}

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
        features_ok = bool(features.get("ok"))
        ambiguity = SuggestAmbiguity(
            clip_family_ambiguous=(not features_ok) or (float(features.get("clip_family_p") or 0.0) < settings.SUGGEST_TYPE_MIN_P),
            clip_pattern_ambiguous=(not features_ok) or (float(features.get("clip_pattern_p") or 0.0) < settings.SUGGEST_PATTERN_MIN_P),
        )
        image_url = payload.image_url if (payload.use_vision and settings.LLM_USE_VISION) else None
        try:
            llm_draft, llm_meta = await suggest_with_provider(
                features if features_ok else {},
                hints,
                list(lock_fields),
                ambiguity=ambiguity,
                image_url=image_url,
            )
            draft_data = _merge_llm_suggestions(draft_data, llm_draft.model_dump(), lock_fields)
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
        llm_tokens=llm_meta.get("tokens") if llm_meta else 0,
        provider=llm_meta.get("provider") if llm_meta else None,
        user_id=user_id,
    )
    session.add(audit)
    await session.commit()

    return SuggestAttributesOut(draft=merged, pending_features=pending_features)
