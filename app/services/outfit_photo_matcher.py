from __future__ import annotations

import hashlib
import base64
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.models import Item, ItemImage, ItemImageFeatures, Outfit, OutfitItem, OutfitPhoto, OutfitPhotoAnalysis
from app.services.clip_embeddings import embed_image
from app.storage.r2 import r2_client, R2_BUCKET
from workers.vision import _open_image


SLOT_MAP = {
    "top": "top",
    "bottom": "bottom",
    "onepiece": "onepiece",
    "outerwear": "outerwear",
    "footwear": "shoes",
    "accessory": "accessory",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch_photo_bytes(photo: OutfitPhoto) -> Optional[bytes]:
    if photo.key:
        try:
            s3 = r2_client()
            obj = s3.get_object(Bucket=photo.bucket or R2_BUCKET, Key=photo.key)
            return obj["Body"].read()
        except Exception:
            return None
    if photo.image_url:
        try:
            resp = requests.get(photo.image_url, timeout=5)
            resp.raise_for_status()
            return resp.content
        except Exception:
            return None
    return None


async def analyze_outfit_photo(session: AsyncSession, photo: OutfitPhoto) -> Dict[str, Any]:
    data = _fetch_photo_bytes(photo)
    if not data:
        return {"ok": False, "error": "photo_fetch_failed"}

    sha = _sha256(data)
    b64 = base64.b64encode(data).decode()
    pil_img, err = _open_image(None, b64)
    if not pil_img:
        return {"ok": False, "error": f"decode_failed:{err}"}

    emb = embed_image(pil_img)
    topk = settings.OUTFIT_PHOTO_TOPK_IMAGES
    topn = settings.OUTFIT_PHOTO_TOPN_ITEMS
    min_sim = settings.OUTFIT_PHOTO_MATCH_MIN_SIM

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
            ItemImage.user_id == photo.user_id,
            ItemImageFeatures.embedding.is_not(None),
            ItemImageFeatures.features_version == settings.IMGPROC_FEATURES_VERSION,
        )
        .order_by(distance_expr.asc())
        .limit(topk)
    )
    rows = res.all()
    candidates = [
        {"item_image_id": str(r[0]), "item_id": str(r[1]), "score": float(r[2])}
        for r in rows
    ]

    per_item: Dict[str, float] = {}
    for cand in candidates:
        item_id = cand["item_id"]
        per_item[item_id] = max(per_item.get(item_id, 0.0), cand["score"])
    ranked_items = sorted(per_item.items(), key=lambda x: x[1], reverse=True)[:topn]
    matched = [{"item_id": item_id, "score": score} for item_id, score in ranked_items if score >= min_sim]

    slot_items: List[Dict[str, Any]] = []
    warnings: List[str] = []
    if matched:
        item_ids = [m["item_id"] for m in matched]
        res = await session.execute(select(Item).where(Item.id.in_(item_ids)))
        items = {str(i.id): i for i in res.scalars().all()}
        slot_seen: Dict[str, int] = {}
        for entry in matched:
            item = items.get(entry["item_id"])
            if not item or not item.category:
                continue
            slot = SLOT_MAP.get(item.category, "accessory")
            slot_seen[slot] = slot_seen.get(slot, 0) + 1
            if slot_seen[slot] > settings.OUTFIT_PHOTO_MAX_PER_SLOT:
                continue
            slot_items.append({"item_id": entry["item_id"], "score": entry["score"], "slot": slot})

    if not slot_items:
        warnings.append("NO_ITEMS_MATCHED")
    elif len(slot_items) < 2:
        warnings.append("PARTIAL_MATCH")

    matched_outfit_id = None
    if len(slot_items) >= 2:
        item_set = {m["item_id"] for m in slot_items}
        res = await session.execute(
            select(Outfit)
            .where(Outfit.user_id == photo.user_id)
        )
        outfits = res.scalars().all()
        for outfit in outfits:
            outfit_ids = {str(oi.item_id) for oi in outfit.items}
            if outfit_ids == item_set:
                matched_outfit_id = outfit.id
                break

    return {
        "ok": True,
        "sha": sha,
        "candidates": candidates,
        "matched_items": slot_items,
        "matched_outfit_id": matched_outfit_id,
        "warnings": warnings,
        "debug": {
            "topk": topk,
            "topn": topn,
            "min_sim": min_sim,
        },
        "width": pil_img.width,
        "height": pil_img.height,
    }


async def persist_outfit_photo_analysis(session: AsyncSession, photo: OutfitPhoto) -> OutfitPhotoAnalysis:
    result = await analyze_outfit_photo(session, photo)
    if not result.get("ok"):
        photo.status = "failed"
        photo.error = result.get("error")
        await session.commit()
        await session.refresh(photo)
        raise RuntimeError(result.get("error") or "analysis_failed")

    photo.status = "done"
    photo.image_hash = result.get("sha")
    photo.width = result.get("width")
    photo.height = result.get("height")
    analysis = OutfitPhotoAnalysis(
        user_id=photo.user_id,
        outfit_photo_id=photo.id,
        method="clip_embed_v1",
        candidates_json={"candidates": result.get("candidates")},
        matched_items_json={"items": result.get("matched_items")},
        matched_outfit_id=result.get("matched_outfit_id"),
        warnings_json=result.get("warnings"),
        debug_json=result.get("debug"),
    )
    session.add(analysis)
    await session.commit()
    await session.refresh(analysis)
    return analysis
