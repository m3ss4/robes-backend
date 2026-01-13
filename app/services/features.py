from __future__ import annotations

import time
import hashlib
from typing import Any, Dict, Optional, Tuple, List

from app.core.config import settings
from workers.vision import extract_features, _open_image
from app.services.clip_classifier import classify_image

# Simple in-process cache keyed by image hash
_FEATURE_CACHE: dict[str, tuple[float, Dict[str, Any]]] = {}
_CACHE_TTL = 300  # seconds


def _image_hash(image_url: Optional[str], image_b64: Optional[str]) -> Optional[str]:
    if image_b64:
        return hashlib.md5(image_b64.encode()).hexdigest()
    if image_url:
        return hashlib.md5(image_url.encode()).hexdigest()
    return None


def _combine_hashes(hashes: List[str]) -> str:
    h = hashlib.md5()
    for val in sorted(hashes):
        h.update(val.encode())
    return h.hexdigest()


async def load_features(
    image_url: Optional[str],
    image_b64: Optional[str],
    image_urls: Optional[List[str]] = None,
    image_b64s: Optional[List[str]] = None,
    item_id: Optional[str] = None,
    image_ids: Optional[List[str]] = None,
    session: Optional[Any] = None,
    wait_ms: int = 0,
) -> Tuple[Dict[str, Any], bool]:
    """
    Placeholder feature loader. Intended to be replaced by DB-backed image analysis results.
    Returns (features, pending_flag). Currently uses synchronous vision heuristics + CLIP.
    Supports multiple images by aggregating scores.
    """
    _ = wait_ms  # reserved for future polling
    urls = image_urls or []
    b64s = image_b64s or []
    if image_url:
        urls = [image_url] + urls
    if image_b64:
        b64s = [image_b64] + b64s

    inputs: List[tuple[Optional[str], Optional[str]]] = []
    if urls:
        for idx, u in enumerate(urls):
            b = b64s[idx] if idx < len(b64s) else None
            inputs.append((u, b))
    elif b64s:
        inputs = [(None, b) for b in b64s]
    else:
        inputs = [(image_url, image_b64)]

    hashes = [h for h in (_image_hash(u, b) for u, b in inputs) if h]
    cache_key = _combine_hashes(hashes) if hashes else None
    now = time.time()
    # Attempt DB-backed load if session and image_ids provided
    if session and (image_ids or item_id):
        from app.services import feature_store

        ids = image_ids or []
        if not ids and item_id:
            db_feats = await feature_store.get_latest_for_item(session, item_id)
        else:
            db_feats = list((await feature_store.get_for_images(session, ids)).values())
        if not db_feats and ids:
            db_feats = list((await feature_store.wait_for_any(session, ids, timeout_ms=wait_ms or settings.LLM_SUGGEST_TIMEOUT_MS)).values())
        if db_feats:
            f = db_feats[0]
            data = {
                "ok": True,
                "category": f.family_pred,
                "base_color": f.dominant_color_name,
                "pattern": f.pattern_pred,
                "pattern_confidence": f.pattern_p,
                "clip_family": f.family_pred,
                "clip_family_p": f.family_p,
                "clip_type": f.type_pred,
                "clip_type_p": f.type_p,
                "clip_type_top3": f.type_top3,
                "clip_pattern": f.pattern_pred,
                "clip_pattern_p": f.pattern_p,
                "clip_pattern_top3": f.pattern_scores,
                "features_version": f.features_version,
                "feature_source": "store",
            }
            return data, False
        else:
            pending = True  # requested stored features but none yet

    if cache_key and cache_key in _FEATURE_CACHE:
        ts, cached_feats = _FEATURE_CACHE[cache_key]
        if now - ts < _CACHE_TTL:
            return cached_feats, False
        _FEATURE_CACHE.pop(cache_key, None)

    started = time.time()
    feats_list = []
    pending = False
    for u, b in inputs:
        feats = extract_features(u, b)
        img_obj = None
        if u or b:
            img_obj, _ = _open_image(u, b)
        if img_obj:
            try:
                clip_res = classify_image(img_obj, family_hint=feats.get("category"))
                feats.update(clip_res)
            except Exception:
                pass
        if not feats.get("ok") and (u or b):
            pending = True
        feats_list.append(feats)

    agg: Dict[str, Any] = {}

    def pick_max(key: str, conf_key: str) -> tuple[Optional[Any], float]:
        best_val, best_conf = None, 0.0
        for f in feats_list:
            conf = f.get(conf_key) or 0.0
            if conf > best_conf and f.get(key):
                best_val, best_conf = f.get(key), conf
        return best_val, best_conf

    agg["clip_family"], agg["clip_family_p"] = pick_max("clip_family", "clip_family_p")
    agg["clip_type"], agg["clip_type_p"] = pick_max("clip_type", "clip_type_p")
    agg["clip_pattern"], agg["clip_pattern_p"] = pick_max("clip_pattern", "clip_pattern_p")
    best_ft = max(feats_list, key=lambda f: f.get("clip_type_p", 0.0)) if feats_list else {}
    agg["clip_type_top3"] = best_ft.get("clip_type_top3")
    agg["clip_pattern_top3"] = best_ft.get("clip_pattern_top3")

    primary = next((f for f in feats_list if f.get("ok")), feats_list[0] if feats_list else {})
    agg.update(primary)

    agg["features_version"] = settings.IMGPROC_FEATURES_VERSION
    agg["latency_ms"] = int((time.time() - started) * 1000)
    agg["feature_source"] = "inline"
    # Persist if we have a DB session and image_ids
    if session and image_ids:
        from app.services import feature_store

        first_id = image_ids[0] if image_ids else None
        if first_id:
            payload = {
                "features_version": settings.IMGPROC_FEATURES_VERSION,
                "dominant_color_name": agg.get("base_color"),
                "edge_density": agg.get("edge_density"),
                "stripe_score": agg.get("stripe_score"),
                "plaid_score": agg.get("plaid_score"),
                "dot_score": agg.get("dot_score"),
                "family_pred": agg.get("clip_family"),
                "family_p": agg.get("clip_family_p"),
                "type_pred": agg.get("clip_type"),
                "type_p": agg.get("clip_type_p"),
                "type_top3": agg.get("clip_type_top3"),
                "pattern_pred": agg.get("clip_pattern") or agg.get("pattern"),
                "pattern_p": agg.get("clip_pattern_p") or agg.get("pattern_confidence"),
                "pattern_scores": agg.get("clip_pattern_top3"),
                "width": (agg.get("debug_dims") or {}).get("width"),
                "height": (agg.get("debug_dims") or {}).get("height"),
            }
            try:
                await feature_store.upsert(session, first_id, payload)
                await session.commit()
            except Exception:
                await session.rollback()
                # swallow; best-effort persistence
                pass
    if cache_key:
        _FEATURE_CACHE[cache_key] = (now, agg)
    return agg, pending
