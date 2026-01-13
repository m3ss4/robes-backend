from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Item, OutfitWearLog, OutfitWearLogItem
from sqlalchemy import func

SLOT_NAMES = {"top", "bottom", "one_piece", "outerwear", "shoes", "bag", "accessory"}

EVENT_FORMALITY = {
    "black-tie": 0.95,
    "formal": 0.85,
    "business-formal": 0.8,
    "office": 0.65,
    "business-casual": 0.6,
    "smart-casual": 0.55,
    "casual": 0.4,
    "gym": 0.2,
    "hiking": 0.3,
    "outdoor": 0.4,
}


async def fetch_items(session: AsyncSession, user_id: str, item_ids: List[str]) -> Dict[str, Item]:
    if not item_ids:
        return {}
    res = await session.execute(select(Item).where(Item.user_id == user_id, Item.id.in_(item_ids)))
    return {str(i.id): i for i in res.scalars().all()}


async def score_outfit(
    session: AsyncSession, user_id: str, items: List[Dict[str, Any]], context: Dict[str, Any] | None
) -> Dict[str, Any]:
    context = context or {}
    item_ids = [it["item_id"] for it in items]
    item_map = await fetch_items(session, user_id, item_ids)

    slots = {it["slot"] for it in items}
    completeness = 1.0 if ("shoes" in slots and (("one_piece" in slots) or ("top" in slots and "bottom" in slots))) else 0.0

    target_formality = _target_formality(context.get("event"))
    avg_formality = _avg(
        [
            item_map[it["item_id"]].formality
            for it in items
            if item_map.get(it["item_id"]) and item_map[it["item_id"]].formality is not None
        ],
        default=0.5,
    )
    formality_score = max(0.0, 1 - abs((avg_formality or 0.5) - target_formality))

    season_ctx = (context.get("season") or "").lower() or None
    season_match = 0.5
    if season_ctx:
        hits = 0
        for it in items:
            item = item_map.get(it["item_id"])
            if item and item.season_tags and season_ctx in [s.lower() for s in item.season_tags]:
                hits += 1
        season_match = hits / len(items) if items else 0.5

    weather_score, weather_expl = _weather_score(context.get("weather"), items, item_map)
    rotation = await _rotation_score(session, user_id, item_ids)

    colors = [
        item_map[it["item_id"]].base_color
        for it in items
        if item_map.get(it["item_id"]) and item_map[it["item_id"]].base_color
    ]
    unique_colors = len(set(colors)) or 1
    color_score = max(0.3, 1.0 - (unique_colors - 1) * 0.1)

    dims = {
        "completeness": round(completeness, 2),
        "event": round(formality_score, 2),
        "season": round(season_match, 2),
        "rotation": round(rotation, 2),
        "color": round(color_score, 2),
        "weather": round(weather_score, 2),
    }
    total = round(sum(dims.values()) / len(dims), 2)
    explanations = []
    explanations.append(f"Formality {avg_formality:.2f} vs target {target_formality:.2f}")
    explanations.append(f"Colors: {', '.join(set(colors)) or 'neutral'}")
    explanations.append(f"Rotation score {rotation:.2f}")
    if weather_expl:
        explanations.append(weather_expl)
    return {"total": total, "dims": dims, "explanations": explanations}


def _avg(vals, default=0.0):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else default


async def _rotation_score(session: AsyncSession, user_id: str, item_ids: List[str]) -> float:
    if not item_ids:
        return 0.5
    res = await session.execute(
        select(func.max(OutfitWearLog.worn_at))
        .select_from(OutfitWearLog)
        .join(OutfitWearLogItem, OutfitWearLogItem.wear_log_id == OutfitWearLog.id)
        .where(OutfitWearLog.user_id == user_id, OutfitWearLogItem.item_id.in_(item_ids))
    )
    last = res.scalar_one_or_none()
    if not last:
        return 0.85
    # Penalize if worn very recently (<3 days)
    delta_days = (datetime.now(timezone.utc) - last).days
    if delta_days < 2:
        return 0.3
    if delta_days < 7:
        return 0.6
    if delta_days < 30:
        return 0.8
    return 0.9


def _target_formality(event: str | None) -> float:
    if not event:
        return 0.5
    return EVENT_FORMALITY.get(event, 0.5)


def _weather_score(weather: Dict[str, Any] | None, items: List[Dict[str, Any]], item_map: Dict[str, Item]) -> tuple[float, str]:
    if not weather:
        return 0.5, ""
    temp_c = weather.get("temp_c") or weather.get("feels_like_c")
    if temp_c is None:
        return 0.5, ""
    # simple warmth band: target 0 at ~22C, + for cold, - for heat
    warmth_vals = [
        item_map[it["item_id"]].warmth
        for it in items
        if item_map.get(it["item_id"]) and item_map[it["item_id"]].warmth is not None
    ]
    avg_warmth = _avg(warmth_vals, default=0)
    ideal_warmth = -1 if temp_c >= 28 else 0 if temp_c >= 18 else 1 if temp_c >= 10 else 2
    score = max(0.0, 1 - abs(avg_warmth - ideal_warmth) * 0.25)
    reason = f"Temp {temp_c}°C, warmth {avg_warmth} vs ideal {ideal_warmth}"
    return score, reason
