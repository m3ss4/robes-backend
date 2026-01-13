from .celery_app import celery
from PIL import Image
from io import BytesIO
import base64
import asyncio
import hashlib
import requests

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import ItemImage
from app.services.feature_store import compute_sha256
from app.services import feature_store
from workers.vision import extract_features, _open_image
from app.services.clip_classifier import classify_image

@celery.task(name="tasks.process_image")
def process_image(image_b64: str) -> dict:
    """Example background-removal stub: simply loads image and returns size.
    Replace with real segmentation later."""
    try:
        raw = base64.b64decode(image_b64)
        im = Image.open(BytesIO(raw))
        return {"ok": True, "size": im.size}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@celery.task(name="tasks.analyze_image")
def analyze_image(image_id: str) -> dict:
    """Compute heuristics + CLIP for an image and persist into feature store."""

    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            img = await session.get(ItemImage, image_id)
            if not img:
                return {"ok": False, "error": "image_not_found"}
            # Fetch bytes
            data = None
            if img.key:
                try:
                    import boto3
                    from app.storage.r2 import r2_client, R2_BUCKET

                    s3 = r2_client()
                    obj = s3.get_object(Bucket=img.bucket or R2_BUCKET, Key=img.key)
                    data = obj["Body"].read()
                except Exception as e:
                    return {"ok": False, "error": f"r2_fetch_failed:{e}"}
            elif img.url:
                try:
                    resp = requests.get(img.url, timeout=5)
                    resp.raise_for_status()
                    data = resp.content
                except Exception as e:
                    return {"ok": False, "error": f"url_fetch_failed:{e}"}
            if not data:
                return {"ok": False, "error": "no_data"}

            sha = compute_sha256(data)
            # Decode image
            pil_img, err = _open_image(None, base64.b64encode(data).decode())
            if not pil_img:
                return {"ok": False, "error": f"decode_failed:{err}"}

            feats = extract_features(None, base64.b64encode(data).decode())
            try:
                clip_res = classify_image(pil_img, family_hint=feats.get("category"))
                feats.update(clip_res)
            except Exception:
                pass

            payload = {
                "features_version": settings.IMGPROC_FEATURES_VERSION,
                "dominant_color_name": feats.get("base_color"),
                "edge_density": feats.get("edge_density"),
                "stripe_score": feats.get("stripe_score"),
                "plaid_score": feats.get("plaid_score"),
                "dot_score": feats.get("dot_score"),
                "family_pred": feats.get("clip_family") or feats.get("category"),
                "family_p": feats.get("clip_family_p"),
                "type_pred": feats.get("clip_type") or feats.get("type"),
                "type_p": feats.get("clip_type_p"),
                "type_top3": feats.get("clip_type_top3"),
                "pattern_pred": feats.get("clip_pattern") or feats.get("pattern"),
                "pattern_p": feats.get("clip_pattern_p") or feats.get("pattern_confidence"),
                "pattern_scores": feats.get("clip_pattern_top3"),
                "image_sha256": sha,
                "width": pil_img.width,
                "height": pil_img.height,
            }
            try:
                await feature_store.upsert(session, str(img.id), payload)
                await session.commit()
            except Exception as e:
                await session.rollback()
                return {"ok": False, "error": f"db_upsert_failed:{e}"}
            return {"ok": True, "image_id": str(img.id)}

    return asyncio.run(_run())
