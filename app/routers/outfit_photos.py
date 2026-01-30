from __future__ import annotations

from datetime import datetime, timezone, date as date_type
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from botocore.exceptions import ClientError

from app.auth.deps import get_current_user_id
from app.core.config import settings
from app.core.db import get_session
from app.models.models import (
    Outfit,
    OutfitItem,
    OutfitPhoto,
    OutfitPhotoAnalysis,
    OutfitRevision,
    OutfitWearLog,
    OutfitWearLogItem,
    ItemWearLog,
)
from app.schemas.schemas import (
    OutfitPhotoPresignIn,
    OutfitPhotoPresignOut,
    OutfitPhotoConfirmIn,
    OutfitPhotoGetOut,
    OutfitPhotoOut,
    OutfitPhotoAnalysisOut,
    OutfitPhotoApplyIn,
    OutfitPhotoApplyOut,
    OutfitPhotoMatchedItem,
)
from app.storage.keys import outfit_photo_key
from app.storage.r2 import presign_put, object_url, presign_get, r2_client, R2_BUCKET
from workers.tasks import analyze_outfit_photo


router = APIRouter(prefix="/outfit-photos", tags=["outfit-photos"])


def _compute_worn_times(date_str: str | None) -> tuple[datetime, date_type]:
    from zoneinfo import ZoneInfo

    tz_london = ZoneInfo("Europe/London")
    if date_str:
        try:
            dt_date = datetime.fromisoformat(date_str).date()
        except Exception:
            dt_date = datetime.now(timezone.utc).date()
        dt = datetime.combine(dt_date, datetime.min.time(), tzinfo=timezone.utc)
    else:
        dt = datetime.now(timezone.utc)
    worn_date = dt.astimezone(tz_london).date()
    return dt, worn_date


@router.post("/presign", response_model=OutfitPhotoPresignOut)
async def presign_outfit_photo(
    body: OutfitPhotoPresignIn,
    user_id: str = Depends(get_current_user_id),
):
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/heic": "heic",
        "image/heif": "heif",
    }.get(body.content_type, "jpg")
    key = outfit_photo_key(str(user_id), ext)
    upload_url, headers = presign_put(key, body.content_type)
    return OutfitPhotoPresignOut(key=key, upload_url=upload_url, headers=headers, cdn_url=object_url(key))


@router.post("/confirm")
async def confirm_outfit_photo(
    body: OutfitPhotoConfirmIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    s3 = r2_client()
    try:
        head = s3.head_object(Bucket=R2_BUCKET, Key=body.key)
    except ClientError as e:
        raise HTTPException(status_code=400, detail="object_not_found") from e
    url = object_url(body.key)
    photo = OutfitPhoto(
        user_id=user_id,
        bucket=R2_BUCKET,
        key=body.key,
        image_url=url,
        width=body.width,
        height=body.height,
        status="pending",
    )
    session.add(photo)
    await session.commit()
    await session.refresh(photo)
    try:
        analyze_outfit_photo.apply_async(args=[str(photo.id)], queue="images")
    except Exception:
        pass
    return {"outfit_photo_id": str(photo.id), "status": photo.status}


@router.get("/{photo_id}", response_model=OutfitPhotoGetOut)
async def get_outfit_photo(
    photo_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    photo = await session.get(OutfitPhoto, photo_id)
    if not photo or str(photo.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="outfit_photo_not_found")
    analysis = None
    res = await session.execute(
        select(OutfitPhotoAnalysis)
        .where(OutfitPhotoAnalysis.outfit_photo_id == photo.id)
        .order_by(OutfitPhotoAnalysis.created_at.desc())
        .limit(1)
    )
    a = res.scalar_one_or_none()
    if a:
        analysis = OutfitPhotoAnalysisOut(
            status=photo.status,
            matched_items=[
                OutfitPhotoMatchedItem(**m) for m in (a.matched_items_json or {}).get("items", [])
            ],
            matched_outfit_id=str(a.matched_outfit_id) if a.matched_outfit_id else None,
            warnings=a.warnings_json or [],
        )
    image_url = photo.image_url or (presign_get(photo.key) if photo.key else None)
    return OutfitPhotoGetOut(
        outfit_photo=OutfitPhotoOut(
            id=str(photo.id),
            status=photo.status,
            created_at=str(photo.created_at),
            image_url=image_url,
        ),
        analysis=analysis,
    )


@router.post("/{photo_id}/apply", response_model=OutfitPhotoApplyOut)
async def apply_outfit_photo(
    photo_id: UUID,
    body: OutfitPhotoApplyIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    photo = await session.get(OutfitPhoto, photo_id)
    if not photo or str(photo.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="outfit_photo_not_found")

    res = await session.execute(
        select(OutfitPhotoAnalysis)
        .where(OutfitPhotoAnalysis.outfit_photo_id == photo.id)
        .order_by(OutfitPhotoAnalysis.created_at.desc())
        .limit(1)
    )
    analysis = res.scalar_one_or_none()
    matched_items = []
    matched_outfit_id = None
    warnings = []
    if analysis:
        matched_items = (analysis.matched_items_json or {}).get("items", [])
        matched_outfit_id = analysis.matched_outfit_id
        warnings = analysis.warnings_json or []
    else:
        warnings = ["NO_ITEMS_MATCHED"]
    if analysis and not matched_items and "NO_ITEMS_MATCHED" not in warnings:
        warnings.append("NO_ITEMS_MATCHED")

    outfit = None
    created = False
    cover_url = photo.image_url or (object_url(photo.key) if photo.key else None)
    if matched_outfit_id and not body.force_create:
        outfit = await session.get(Outfit, matched_outfit_id)
        if outfit and str(outfit.user_id) != str(user_id):
            outfit = None
    if not outfit:
        outfit = Outfit(
            id=uuid4(),
            user_id=user_id,
            status="accepted",
            source="photo_today",
            primary_image_url=cover_url,
        )
        session.add(outfit)
        await session.flush()
        created = True
        for idx, entry in enumerate(matched_items):
            session.add(
                OutfitItem(
                    id=uuid4(),
                    outfit_id=outfit.id,
                    item_id=UUID(entry["item_id"]),
                    slot=entry.get("slot") or "accessory",
                    position=idx,
                )
            )
    else:
        if cover_url:
            outfit.primary_image_url = cover_url

    worn_at, worn_date = _compute_worn_times(body.date)
    existing = await session.execute(
        select(OutfitWearLog).where(
            OutfitWearLog.user_id == user_id,
            OutfitWearLog.outfit_id == outfit.id,
            OutfitWearLog.worn_date == worn_date,
            OutfitWearLog.deleted_at.is_(None),
        )
    )
    log = existing.scalar_one_or_none()
    outfit_items = []
    res_items = await session.execute(select(OutfitItem).where(OutfitItem.outfit_id == outfit.id))
    outfit_items = res_items.scalars().all()
    if not log:
        items_snapshot = [
            {"item_id": str(oi.item_id), "slot": oi.slot, "position": oi.position}
            for oi in outfit_items
        ]
        rev_no = 1
        res_rev = await session.execute(select(func.max(OutfitRevision.rev_no)).where(OutfitRevision.outfit_id == outfit.id))
        max_rev = res_rev.scalar_one_or_none()
        if max_rev:
            rev_no = max_rev + 1
        rev = OutfitRevision(
            id=uuid4(),
            outfit_id=outfit.id,
            rev_no=rev_no,
            items_snapshot=items_snapshot,
            attributes_snapshot=outfit.attributes,
            metrics_snapshot=outfit.metrics,
        )
        session.add(rev)
        await session.flush()
        log = OutfitWearLog(
            id=uuid4(),
            user_id=user_id,
            outfit_id=outfit.id,
            outfit_revision_id=rev.id,
            worn_at=worn_at,
            worn_date=worn_date,
            source="photo_today",
        )
        session.add(log)
        await session.flush()
        for oi in outfit_items:
            session.add(OutfitWearLogItem(wear_log_id=log.id, item_id=oi.item_id, slot=oi.slot))

    for entry in matched_items:
        item_id = UUID(entry["item_id"])
        res = await session.execute(
            select(ItemWearLog).where(
                ItemWearLog.user_id == user_id,
                ItemWearLog.item_id == item_id,
                ItemWearLog.worn_date == worn_date,
                ItemWearLog.deleted_at.is_(None),
            )
        )
        existing_item = res.scalar_one_or_none()
        if not existing_item:
            session.add(
                ItemWearLog(
                    id=uuid4(),
                    user_id=user_id,
                    item_id=item_id,
                    worn_at=worn_at,
                    worn_date=worn_date,
                    source="photo_today",
                )
            )

    await session.commit()

    message = None
    if "NO_ITEMS_MATCHED" in warnings:
        message = "Saved outfit photo. Add individual items to improve matching."
    elif "PARTIAL_MATCH" in warnings:
        message = "Saved outfit photo. Add missing items to improve matching."

    return OutfitPhotoApplyOut(
        outfit_id=str(outfit.id),
        created=created,
        wore_logged=True,
        matched_items=[OutfitPhotoMatchedItem(**m) for m in matched_items],
        warnings=warnings,
        message=message,
    )


@router.post("/{photo_id}/requeue")
async def requeue_outfit_photo(
    photo_id: UUID,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    photo = await session.get(OutfitPhoto, photo_id)
    if not photo or str(photo.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="outfit_photo_not_found")
    photo.status = "pending"
    photo.error = None
    await session.commit()
    try:
        analyze_outfit_photo.apply_async(args=[str(photo.id)], queue="images")
    except Exception:
        pass
    return {"outfit_photo_id": str(photo.id), "status": photo.status}
