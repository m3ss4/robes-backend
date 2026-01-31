from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.auth.deps import get_current_user_id
from app.core.config import settings
from app.core.db import get_session
from app.schemas.schemas import (
    OutfitMatchIn,
    OutfitMatchOut,
    OutfitMatchItemOut,
    OutfitMatchQueueIn,
    OutfitMatchJobOut,
    OutfitMatchJobListOut,
)
from app.services.outfit_item_matcher import match_outfit_image
from app.models.models import OutfitMatchJob
from workers.tasks import analyze_outfit_match_job

router = APIRouter(prefix="/outfit-match", tags=["outfit-match"])


@router.post("", response_model=OutfitMatchOut)
async def match_outfit_items(
    payload: OutfitMatchIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    if not settings.LLM_ENABLED or not settings.LLM_USE_VISION:
        raise HTTPException(status_code=400, detail="llm_vision_disabled")
    if not payload.image_url and not payload.image_b64:
        raise HTTPException(status_code=400, detail="image_required")

    min_conf = float(payload.min_confidence or settings.OUTFIT_MATCH_MIN_CONFIDENCE)
    max_per_slot = int(payload.max_per_slot or settings.OUTFIT_MATCH_MAX_PER_SLOT)
    if max_per_slot < 1:
        raise HTTPException(status_code=400, detail="invalid_max_per_slot")

    result = await match_outfit_image(
        session,
        user_id,
        image_url=payload.image_url,
        image_b64=payload.image_b64,
        image_content_type=payload.image_content_type,
        min_confidence=min_conf,
        max_per_slot=max_per_slot,
    )
    return OutfitMatchOut(
        matches=[OutfitMatchItemOut(**m) for m in result.get("matches", [])],
        slots=result.get("slots", []),
        missing_count=int(result.get("missing_count") or 0),
        warnings=result.get("warnings", []),
        usage=result.get("usage"),
    )


@router.post("/queue", response_model=OutfitMatchJobOut)
async def queue_outfit_match(
    payload: OutfitMatchQueueIn,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    if not settings.LLM_ENABLED or not settings.LLM_USE_VISION:
        raise HTTPException(status_code=400, detail="llm_vision_disabled")
    try:
        worn_date = date.fromisoformat(payload.date) if payload.date else None
    except Exception as e:
        raise HTTPException(status_code=400, detail="invalid_date") from e

    res = await session.execute(
        select(OutfitMatchJob).where(
            OutfitMatchJob.user_id == user_id,
            OutfitMatchJob.image_url == payload.image_url,
            OutfitMatchJob.worn_date == worn_date,
            OutfitMatchJob.status.in_(["queued", "processing", "done"]),
        )
    )
    existing = res.scalar_one_or_none()
    if existing:
        matches = None
        if existing.status == "done":
            matches = [OutfitMatchItemOut(**m) for m in (existing.matches_json or [])]
        elif existing.matches_json:
            matches = [OutfitMatchItemOut(**m) for m in (existing.matches_json or [])]
        return OutfitMatchJobOut(
            job_id=str(existing.id),
            status=existing.status,
            image_url=existing.image_url,
            date=str(existing.worn_date) if existing.worn_date else None,
            matches=matches,
            slots=existing.slots_json,
            warnings=existing.warnings_json,
            error=existing.error,
        )

    job = OutfitMatchJob(
        user_id=user_id,
        image_url=payload.image_url,
        worn_date=worn_date,
        status="queued",
        min_confidence=payload.min_confidence,
        max_per_slot=payload.max_per_slot,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    analyze_outfit_match_job.apply_async(args=[str(job.id)], queue="images")
    return OutfitMatchJobOut(
        job_id=str(job.id),
        status=job.status,
        image_url=job.image_url,
        date=str(job.worn_date) if job.worn_date else None,
        matches=None,
        slots=None,
        warnings=None,
        error=None,
    )


@router.get("/{job_id}", response_model=OutfitMatchJobOut)
async def get_outfit_match_job(
    job_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    job = await session.get(OutfitMatchJob, job_id)
    if not job or str(job.user_id) != str(user_id):
        raise HTTPException(status_code=404, detail="outfit_match_job_not_found")
    return OutfitMatchJobOut(
        job_id=str(job.id),
        status=job.status,
        image_url=job.image_url,
        date=str(job.worn_date) if job.worn_date else None,
        matches=[OutfitMatchItemOut(**m) for m in (job.matches_json or [])] if job.matches_json else None,
        slots=job.slots_json,
        warnings=job.warnings_json,
        error=job.error,
    )


@router.get("", response_model=OutfitMatchJobListOut)
async def list_outfit_match_jobs(
    status: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    statuses = [s.strip() for s in status.split(",")] if status else ["queued", "processing"]
    res = await session.execute(
        select(OutfitMatchJob)
        .where(
            and_(
                OutfitMatchJob.user_id == user_id,
                OutfitMatchJob.status.in_(statuses),
            )
        )
        .order_by(OutfitMatchJob.created_at.desc())
    )
    jobs = res.scalars().all()
    return OutfitMatchJobListOut(
        jobs=[
            OutfitMatchJobOut(
                job_id=str(job.id),
                status=job.status,
                image_url=job.image_url,
                date=str(job.worn_date) if job.worn_date else None,
                matches=[OutfitMatchItemOut(**m) for m in (job.matches_json or [])] if job.matches_json else None,
                slots=job.slots_json,
                warnings=job.warnings_json,
                error=job.error,
            )
            for job in jobs
        ]
    )
