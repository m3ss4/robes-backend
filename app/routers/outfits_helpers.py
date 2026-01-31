from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.models.models import Item


def _slot_for_item(item: Item) -> str:
    kind = item.kind
    if kind == "onepiece":
        return "one_piece"
    if kind == "outerwear":
        return "outerwear"
    if kind == "footwear":
        return "shoes"
    if kind == "accessory":
        return "accessory"
    if kind == "top":
        return "top"
    if kind == "bottom":
        return "bottom"
    return "accessory"


def _filtered_candidates(items: list[Item], ctx: dict) -> dict[str, list[str]]:
    event = (ctx.get("event") or "").lower()
    season = (ctx.get("season") or "").lower()
    cmap: dict[str, list[tuple[int, str]]] = {}
    for it in items:
        slot = _slot_for_item(it)
        score = 0
        if event and it.event_tags and event in [e.lower() for e in it.event_tags]:
            score += 2
        if season and it.season_tags and season in [s.lower() for s in it.season_tags]:
            score += 1
        if it.base_color in {"black", "white", "navy", "gray"}:
            score += 1
        cmap.setdefault(slot, []).append((score, str(it.id)))
    # sort by score desc, then id
    out: dict[str, list[str]] = {}
    for slot, vals in cmap.items():
        vals.sort(key=lambda x: x[0], reverse=True)
        out[slot] = [v[1] for v in vals[:20]]
    return out


def _pattern_ok(sel: list[dict], item_lookup: dict[str, Item]) -> bool:
    patterned = 0
    for s in sel:
        item = item_lookup.get(s["item_id"])
        if item and item.pattern and item.pattern != "solid":
            patterned += 1
    return patterned <= 1


def _normalize_feel_tags(tags: list[str]) -> list[str]:
    cleaned = []
    for tag in tags or []:
        if not tag:
            continue
        trimmed = tag.strip()
        if trimmed:
            cleaned.append(trimmed[:32])
    return cleaned[:12]


def _item_descriptors(sel: list[dict], item_lookup: dict[str, Item]) -> list[dict]:
    descs = []
    for s in sel:
        item = item_lookup.get(s["item_id"])
        if not item:
            continue
        descs.append(
            {
                "slot": s["slot"],
                "base_color": item.base_color,
                "pattern": item.pattern,
                "material": item.material,
                "name": item.name or "",
            }
        )
    return descs


def _compute_worn_times(
    worn_at_str: Optional[str],
    worn_date_str: Optional[str] = None,
) -> tuple[datetime, datetime.date]:
    from zoneinfo import ZoneInfo

    tz_london = ZoneInfo("Europe/London")
    dt_date = None
    if worn_date_str:
        try:
            dt_date = datetime.fromisoformat(worn_date_str).date()
        except Exception:
            dt_date = None
    if worn_at_str:
        try:
            dt = datetime.fromisoformat(worn_at_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        if dt_date:
            dt = datetime.combine(dt_date, datetime.min.time(), tzinfo=timezone.utc)
        else:
            dt = datetime.now(timezone.utc)
    worn_date = dt_date or dt.astimezone(tz_london).date()
    return dt, worn_date
