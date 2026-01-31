from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.core.config import settings
from app.core.tags import ALLOWED_EVENTS, ALLOWED_SEASONS, clamp_limits, normalize_many, normalize_tag
from app.core.taxonomy import get_taxonomy
from app.models.models import Item, ItemImage
from app.schemas.schemas import ItemOut
from app.storage.r2 import presign_get, object_url, R2_BUCKET, R2_CDN_BASE


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
PAIRING_CATEGORIES = {"top", "bottom"}

TYPE_TO_CATEGORY = {
    "tshirt": "top",
    "shirt": "top",
    "blouse": "top",
    "knit": "top",
    "hoodie": "top",
    "sweatshirt": "top",
    "polo": "top",
    "tank": "top",
    "jeans": "bottom",
    "trousers": "bottom",
    "chinos": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "dress": "onepiece",
    "jumpsuit": "onepiece",
    "jacket": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "raincoat": "outerwear",
    "puffer": "outerwear",
    "gilet": "outerwear",
    "sneakers": "footwear",
    "boots": "footwear",
    "loafers": "footwear",
    "heels": "footwear",
    "sandals": "footwear",
}
MAX_PAIRING_LIMIT = 30


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


def _pairing_key_for_category(category: str) -> str:
    if category not in PAIRING_CATEGORIES:
        raise ValueError("unsupported_category")
    return "bottom" if category == "top" else "top"


def _normalize_pairing_list(raw: list[dict]) -> list[dict]:
    cleaned = []
    seen: set[str] = set()
    for entry in raw or []:
        item_id = str(entry.get("item_id") or "").strip()
        if not item_id or item_id in seen:
            continue
        try:
            score = float(entry.get("score", 0))
        except Exception:
            score = 0.0
        score = max(0.0, min(score, 100.0))
        if score < settings.PAIRING_MIN_SCORE:
            continue
        cleaned.append({"item_id": item_id, "score": score})
        seen.add(item_id)
    cleaned.sort(key=lambda x: x["score"], reverse=True)
    return cleaned


def _upsert_pairing_entry(entries: list[dict], item_id: str, score: float) -> list[dict]:
    updated = False
    for entry in entries:
        if entry.get("item_id") == item_id:
            entry["score"] = max(0.0, min(float(score), 100.0))
            updated = True
            break
    if not updated:
        entries.append({"item_id": item_id, "score": max(0.0, min(float(score), 100.0))})
    return _normalize_pairing_list(entries)


def _build_item_attributes(item: Item) -> dict:
    return {
        "id": str(item.id),
        "category": item.category,
        "kind": item.kind,
        "status": item.status,
        "type": item.item_type,
        "fit": item.fit,
        "fabric_kind": item.fabric_kind,
        "pattern": item.pattern,
        "tone": item.tone,
        "layer_role": item.layer_role,
        "name": item.name,
        "brand": item.brand,
        "base_color": item.base_color,
        "material": item.material,
        "warmth": item.warmth,
        "formality": item.formality,
        "style_tags": item.style_tags or [],
        "event_tags": item.event_tags or [],
        "season_tags": item.season_tags or [],
    }


def _build_attribute_sources(item: Item) -> dict:
    sources = item.attribute_sources or {}
    out: dict[str, dict[str, float | str]] = {}
    for field, meta in sources.items():
        src = meta.get("source") if isinstance(meta, dict) else None
        if src == "user":
            confidence = 1.0
        elif src == "suggested":
            confidence = 0.6
        else:
            confidence = 0.8
        out[field] = {"source": src or "unknown", "confidence": confidence}
    return out


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
            if R2_CDN_BASE:
                return f"{R2_CDN_BASE}/{img.key}"
            return presign_get(img.key, bucket=img.bucket or R2_BUCKET)
        except Exception:
            pass
    if img.url:
        return img.url
    return ""


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
        for img in getattr(item, "images", [])
    ]
    return ItemOut(
        id=str(item.id),
        kind=item.kind,
        status=item.status,
        attribute_sources=item.attribute_sources,
        pairing_suggestions=item.pairing_suggestions,
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


def _ext_from_content_type(ct: str) -> str:
    return {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }.get(ct, "jpg")


def _default_draft(hints: Dict[str, Any], features: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    base_color = hints.get("base_color") or features.get("base_color") or None
    clip_type_ok = (features.get("clip_type_p") or 0) >= settings.SUGGEST_TYPE_MIN_P
    type_guess = hints.get("type") or (features.get("clip_type") if clip_type_ok else None)
    type_source = "hint" if hints.get("type") else ("clip" if type_guess else "sanity")
    if hints.get("category"):
        category = hints.get("category")
    elif type_guess and type_source in {"clip", "hint", "locked", "user", "rule"}:
        category = TYPE_TO_CATEGORY.get(type_guess)
    elif (features.get("clip_family_p") or 0) >= settings.SUGGEST_FAMILY_MIN_P:
        category = features.get("clip_family")
    else:
        category = None
    tone = hints.get("tone") or features.get("tone") or ("cool" if base_color in {"navy", "blue", "black", "gray"} else "warm")
    pattern_guess = hints.get("pattern") or features.get("pattern")
    clip_pattern_p = features.get("clip_pattern_p") or 0.0
    clip_pattern = features.get("clip_pattern")
    if not pattern_guess and clip_pattern_p >= settings.SUGGEST_PATTERN_MIN_P:
        pattern_guess = clip_pattern
    max_geom = max(features.get("stripe_score") or 0.0, features.get("plaid_score") or 0.0, features.get("dot_score") or 0.0)
    if max_geom < settings.PATTERN_MIN_SCORE and clip_pattern_p < settings.SUGGEST_PATTERN_MIN_P:
        pattern_guess = "solid"
    if pattern_guess == "stripe" and clip_pattern in {"graphic"}:
        if clip_pattern_p >= 0.22:
            pattern_guess = clip_pattern
    base_conf = 0.9 if features.get("base_color") else (0.9 if "base_color" in hints else 0.0)
    tone_conf = 0.8 if features.get("tone") else 0.6
    pattern_conf = features.get("pattern_confidence", 0.0)
    if pattern_guess == clip_pattern:
        pattern_conf = max(pattern_conf, clip_pattern_p)
    formality_guess = hints.get("formality") or features.get("formality") or 0.5
    warmth_guess = hints.get("warmth") or features.get("warmth") or 0
    layer_guess = hints.get("layer_role") or ("outer" if warmth_guess >= 2 else "base")
    reasons = {
        "base_color": features.get("reason") or "dominant color heuristic",
        "tone": "derived from hue/sat",
        "pattern": "contrast heuristic" if features.get("pattern") else "unsure",
        "formality": "priors from type/pattern/color",
    }
    if hints.get("category"):
        cat_source = "hint"
    elif type_guess and type_source in {"clip", "hint", "locked", "user", "rule"}:
        cat_source = "rule"
    elif category == features.get("clip_family"):
        cat_source = "clip"
    else:
        cat_source = "sanity"
    type_reason = "type_below_threshold" if not type_guess else None
    pattern_source = (
        "hint"
        if hints.get("pattern")
        else ("clip" if pattern_guess == features.get("clip_pattern") else "vision" if features.get("pattern") else "rule")
    )

    if type_guess in {"tshirt", "tank", "hoodie", "sweatshirt", "knit"}:
        fabric_kind = {"value": "knit", "confidence": 0.6, "source": "rule"}
    else:
        fabric_kind = {"value": None, "confidence": 0.0, "source": "rule"}

    draft: Dict[str, Dict[str, Any]] = {
        "category": {"value": category, "confidence": 0.9 if "category" in hints else (0.7 if category else 0.0), "source": cat_source},
        "type": {
            "value": type_guess,
            "confidence": (features.get("clip_type_p") or 0.0) if type_source == "clip" else (0.9 if type_source == "hint" else 0.0),
            "source": type_source,
            "reason": type_reason,
        },
        "base_color": {"value": base_color, "confidence": base_conf, "source": "color" if features.get("base_color") else "hint" if hints.get("base_color") else "rule", "reason": reasons["base_color"]},
        "tone": {"value": tone, "confidence": tone_conf, "source": "rule", "reason": reasons["tone"]},
        "warmth": {"value": warmth_guess, "confidence": 0.6, "source": "rule"},
        "formality": {"value": formality_guess, "confidence": 0.65, "source": "rule", "reason": reasons["formality"]},
        "layer_role": {"value": layer_guess, "confidence": 0.7, "source": "rule"},
        "pattern": {"value": pattern_guess, "confidence": max(pattern_conf, features.get("clip_pattern_p") or 0.0), "source": pattern_source, "reason": reasons["pattern"]},
        "fabric_kind": fabric_kind,
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
