from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Item, ItemImage, ItemImageFeatures
from app.services.clip_embeddings import embed_image
from app.services import llm as llm_service
from app.services.llm.types import OutfitSlotDetectInput, OutfitItemMatchInput, OutfitItemMatchCandidate
from app.storage.r2 import presign_get, R2_CDN_BASE
from workers.vision import _open_image


SLOT_CATEGORY_MAP = {
    "onepiece": {"onepiece"},
    "top": {"top"},
    "bottom": {"bottom"},
    "outerwear": {"outerwear"},
    "footwear": {"footwear"},
    "accessory": {"accessory"},
}


def _data_url_from_b64(image_b64: str, content_type: Optional[str]) -> str:
    mime = content_type or "image/jpeg"
    return f"data:{mime};base64,{image_b64}"


def _candidate_image_url(img: ItemImage) -> Optional[str]:
    if img.key:
        if R2_CDN_BASE:
            return f"{R2_CDN_BASE}/{img.key}"
        return presign_get(img.key, expires=settings.LLM_VISION_URL_TTL_S, bucket=img.bucket)
    if img.url:
        return img.url
    return None


def _load_pil_image(image_url: Optional[str], image_b64: Optional[str]) -> Tuple[Optional[Any], Optional[str]]:
    return _open_image(image_url, image_b64)


async def _candidate_items_from_embedding(
    session: AsyncSession,
    user_id: str,
    emb: List[float],
    *,
    topk: int,
    topn: int,
    min_sim: float,
) -> List[Dict[str, Any]]:
    distance_expr = None
    try:
        distance_expr = ItemImageFeatures.embedding.cosine_distance(emb)
    except Exception:
        distance_expr = func.cosine_distance(ItemImageFeatures.embedding, emb)
    score_expr = (1 - distance_expr).label("score")

    res = await session.execute(
        select(ItemImageFeatures.image_id, ItemImage.item_id, score_expr)
        .join(ItemImage, ItemImage.id == ItemImageFeatures.image_id)
        .where(
            ItemImage.user_id == user_id,
            ItemImageFeatures.embedding.is_not(None),
            ItemImageFeatures.features_version == settings.IMGPROC_FEATURES_VERSION,
        )
        .order_by(distance_expr.asc())
        .limit(topk)
    )
    rows = res.all()
    if not rows:
        return []

    per_item: Dict[str, Dict[str, Any]] = {}
    for image_id, item_id, score in rows:
        key = str(item_id)
        score_val = float(score)
        if key not in per_item or score_val > per_item[key]["score"]:
            per_item[key] = {"item_id": key, "image_id": str(image_id), "score": score_val}

    ranked = sorted(per_item.values(), key=lambda x: x["score"], reverse=True)
    if min_sim > 0:
        ranked = [r for r in ranked if r["score"] >= min_sim] or ranked
    ranked = ranked[:topn]

    item_ids = [r["item_id"] for r in ranked]
    image_ids = [r["image_id"] for r in ranked]

    res = await session.execute(select(Item).where(Item.id.in_(item_ids)))
    items = {str(i.id): i for i in res.scalars().all()}
    res = await session.execute(select(ItemImage).where(ItemImage.id.in_(image_ids)))
    images = {str(i.id): i for i in res.scalars().all()}

    candidates: List[Dict[str, Any]] = []
    for r in ranked:
        item = items.get(r["item_id"])
        image = images.get(r["image_id"])
        if not item or not image:
            continue
        image_url = _candidate_image_url(image)
        if not image_url:
            continue
        candidates.append(
            {
                "item_id": str(item.id),
                "category": item.category,
                "type": item.item_type,
                "base_color": item.base_color,
                "pattern": item.pattern,
                "fabric_kind": item.fabric_kind,
                "brand": item.brand,
                "name": item.name,
                "image_url": image_url,
                "similarity": r["score"],
            }
        )
    return candidates


def _fallback_slots(candidates: List[Dict[str, Any]]) -> List[str]:
    present = {c.get("category") for c in candidates if c.get("category")}
    slots = []
    if "onepiece" in present:
        slots.append("onepiece")
    else:
        if "top" in present:
            slots.append("top")
        if "bottom" in present:
            slots.append("bottom")
    if "outerwear" in present:
        slots.append("outerwear")
    if "footwear" in present:
        slots.append("footwear")
    if "accessory" in present:
        slots.append("accessory")
    return slots or ["top", "bottom"]


async def match_outfit_image(
    session: AsyncSession,
    user_id: str,
    *,
    image_url: Optional[str],
    image_b64: Optional[str],
    image_content_type: Optional[str],
    min_confidence: float,
    max_per_slot: int,
) -> Dict[str, Any]:
    if not settings.LLM_ENABLED or not settings.LLM_USE_VISION:
        return {"matches": [], "slots": [], "missing_count": 0, "warnings": ["LLM_DISABLED"], "usage": None}

    pil_img, err = _load_pil_image(image_url, image_b64)
    if not pil_img:
        return {"matches": [], "slots": [], "missing_count": 0, "warnings": [f"IMAGE_LOAD_FAILED:{err}"], "usage": None}

    llm_image_url = image_url
    if not llm_image_url and image_b64:
        llm_image_url = _data_url_from_b64(image_b64, image_content_type)

    if not llm_image_url:
        return {"matches": [], "slots": [], "missing_count": 0, "warnings": ["IMAGE_URL_REQUIRED"], "usage": None}

    emb = embed_image(pil_img)
    candidates = await _candidate_items_from_embedding(
        session,
        user_id,
        emb,
        topk=settings.OUTFIT_MATCH_TOPK_IMAGES,
        topn=settings.OUTFIT_MATCH_TOPN_ITEMS,
        min_sim=settings.OUTFIT_MATCH_MIN_SIM,
    )
    if not candidates:
        return {"matches": [], "slots": [], "missing_count": 0, "warnings": ["NO_CANDIDATES"], "usage": None}

    slot_out = await llm_service.detect_outfit_slots(OutfitSlotDetectInput(image_url=llm_image_url))
    slots = [s for s in slot_out.slots if s in SLOT_CATEGORY_MAP]
    if not slots:
        slots = _fallback_slots(candidates)

    matches: List[Dict[str, Any]] = []
    usage = {"slots": slot_out.usage.model_dump() if slot_out.usage else None, "matches": []}
    for slot in slots:
        categories = SLOT_CATEGORY_MAP.get(slot, set())
        slot_candidates = [c for c in candidates if c.get("category") in categories]
        if not slot_candidates:
            continue
        slot_candidates = sorted(slot_candidates, key=lambda x: x.get("similarity") or 0.0, reverse=True)
        slot_candidates = slot_candidates[:max_per_slot]
        llm_candidates = [
            OutfitItemMatchCandidate(
                item_id=c["item_id"],
                image_url=c["image_url"],
                category=c.get("category"),
                type=c.get("type"),
                base_color=c.get("base_color"),
                pattern=c.get("pattern"),
                fabric_kind=c.get("fabric_kind"),
                brand=c.get("brand"),
                name=c.get("name"),
                similarity=c.get("similarity"),
            )
            for c in slot_candidates
        ]
        match_out = await llm_service.match_outfit_items(
            OutfitItemMatchInput(
                image_url=llm_image_url,
                slot=slot,
                candidates=llm_candidates,
                min_confidence=min_confidence,
            )
        )
        if match_out.usage:
            usage["matches"].append({"slot": slot, "usage": match_out.usage.model_dump()})
        for m in match_out.matches:
            if m.confidence < min_confidence:
                continue
            if not any(c["item_id"] == m.item_id for c in slot_candidates):
                continue
            matches.append(
                {
                    "item_id": m.item_id,
                    "slot": slot,
                    "confidence": float(m.confidence),
                    "reason": m.reason,
                }
            )

    warnings = []
    if not matches:
        warnings.append("NO_HIGH_CONF_MATCHES")

    return {
        "matches": matches,
        "slots": slots,
        "missing_count": int(slot_out.missing_count or 0),
        "warnings": warnings,
        "usage": usage,
    }
