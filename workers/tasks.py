from .celery_app import celery
from PIL import Image
from io import BytesIO
import base64
import asyncio
import hashlib
import requests
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.core.config import settings
from app.models.models import ItemImage, OutfitPhoto, OutfitMatchJob, User
from app.services.feature_store import compute_sha256
from app.services import feature_store
from app.services.outfit_photo_matcher import persist_outfit_photo_analysis
from workers.vision import extract_features, _open_image
from app.services.clip_classifier import classify_image
from app.services.clip_embeddings import embed_image
from app.services.outfit_item_matcher import match_outfit_image

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
            try:
                emb = embed_image(pil_img)
            except Exception:
                emb = None

            payload = {
                "features_version": settings.IMGPROC_FEATURES_VERSION,
                "dominant_color_name": feats.get("base_color"),
                "edge_density": feats.get("edge_density"),
                "stripe_score": feats.get("stripe_score"),
                "plaid_score": feats.get("plaid_score"),
                "dot_score": feats.get("dot_score"),
                "embedding": emb,
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


@celery.task(name="tasks.analyze_outfit_photo")
def analyze_outfit_photo(outfit_photo_id: str) -> dict:
    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            photo = await session.get(OutfitPhoto, outfit_photo_id)
            if not photo:
                return {"ok": False, "error": "outfit_photo_not_found"}
            photo.status = "processing"
            await session.commit()
            try:
                await persist_outfit_photo_analysis(session, photo)
            except Exception as e:
                await session.rollback()
                return {"ok": False, "error": str(e)}
            return {"ok": True, "outfit_photo_id": outfit_photo_id}

    return asyncio.run(_run())


@celery.task(name="tasks.analyze_outfit_match_job")
def analyze_outfit_match_job(job_id: str) -> dict:
    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            job = await session.get(OutfitMatchJob, job_id)
            if not job:
                return {"ok": False, "error": "outfit_match_job_not_found"}
            job.status = "processing"
            await session.commit()
            try:
                result = await match_outfit_image(
                    session,
                    str(job.user_id),
                    image_url=job.image_url,
                    image_b64=None,
                    image_content_type=None,
                    min_confidence=float(job.min_confidence or settings.OUTFIT_MATCH_MIN_CONFIDENCE),
                    max_per_slot=int(job.max_per_slot or settings.OUTFIT_MATCH_MAX_PER_SLOT),
                )
                job.matches_json = result.get("matches")
                job.slots_json = result.get("slots")
                job.warnings_json = result.get("warnings")
                job.error = None
                job.status = "done"
                await session.commit()
                return {"ok": True, "job_id": job_id}
            except Exception as e:
                await session.rollback()
                job.status = "failed"
                job.error = str(e)
                await session.commit()
                return {"ok": False, "error": str(e), "job_id": job_id}

    return asyncio.run(_run())


@celery.task(name="tasks.refresh_user_quality")
def refresh_user_quality(user_id: str) -> dict:
    """Compute and store quality score for a single user."""
    from app.services.quality import QualityEngine

    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            quality_engine = QualityEngine()
            try:
                score, suggestions = await quality_engine.compute_score(
                    session, user_id, persist=True
                )
                return {
                    "ok": True,
                    "user_id": user_id,
                    "score_id": str(score.id),
                    "total_score": score.total_score,
                    "suggestions_count": len(suggestions),
                }
            except Exception as e:
                return {"ok": False, "user_id": user_id, "error": str(e)}

    return asyncio.run(_run())


@celery.task(name="tasks.refresh_all_quality_scores")
def refresh_all_quality_scores() -> dict:
    """Refresh quality scores for all users due for refresh."""
    from app.services.quality import QualityEngine
    from sqlalchemy import select

    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            quality_engine = QualityEngine()

            result = await session.execute(select(User))
            users = result.scalars().all()

            refreshed = 0
            errors = 0

            for user in users:
                prefs = user.quality_preferences or {}
                interval_days = prefs.get(
                    "refresh_interval_days",
                    settings.QUALITY_REFRESH_INTERVAL_DAYS,
                )

                latest = await quality_engine.get_latest_score(session, str(user.id))
                if latest:
                    next_refresh = latest.computed_at + timedelta(days=interval_days)
                    if datetime.now(timezone.utc) < next_refresh:
                        continue

                try:
                    await quality_engine.compute_score(session, str(user.id))
                    refreshed += 1

                    retention = prefs.get(
                        "history_retention_days",
                        settings.QUALITY_HISTORY_RETENTION_DAYS,
                    )
                    await quality_engine.cleanup_old_scores(
                        session, str(user.id), retention
                    )
                except Exception:
                    errors += 1

            return {
                "ok": True,
                "users_checked": len(users),
                "refreshed": refreshed,
                "errors": errors,
            }

    return asyncio.run(_run())


@celery.task(name="tasks.cleanup_quality_history")
def cleanup_quality_history() -> dict:
    """Clean up old quality scores beyond retention period."""
    from app.services.quality import QualityEngine
    from sqlalchemy import select

    async def _run() -> dict:
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            quality_engine = QualityEngine()

            result = await session.execute(select(User))
            users = result.scalars().all()

            total_deleted = 0
            for user in users:
                prefs = user.quality_preferences or {}
                retention = prefs.get(
                    "history_retention_days",
                    settings.QUALITY_HISTORY_RETENTION_DAYS,
                )
                deleted = await quality_engine.cleanup_old_scores(
                    session, str(user.id), retention
                )
                total_deleted += deleted

            return {"ok": True, "deleted": total_deleted}

    return asyncio.run(_run())
