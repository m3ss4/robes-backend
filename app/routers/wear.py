from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user_id
from app.core.db import get_session
from app.models.models import OutfitWearLog, OutfitWearLogItem, ItemWearLog
from app.schemas.schemas import WearPlannedOut, PlannedOutfitWearOut, PlannedItemWearOut

router = APIRouter(prefix="/wear", tags=["wear"])


def _today_london() -> datetime.date:
    tz_london = ZoneInfo("Europe/London")
    return datetime.now(tz_london).date()


@router.get("/today")
async def wear_today(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    today = _today_london()
    res = await session.execute(
        select(OutfitWearLog.outfit_id)
        .where(
            OutfitWearLog.user_id == user_id,
            func.coalesce(OutfitWearLog.worn_date, func.date(OutfitWearLog.worn_at)) == today,
            OutfitWearLog.deleted_at.is_(None),
        )
        .distinct()
    )
    outfit_ids = {str(row[0]) for row in res.all()}

    res = await session.execute(
        select(OutfitWearLogItem.item_id)
        .join(OutfitWearLog, OutfitWearLog.id == OutfitWearLogItem.wear_log_id)
        .where(
            OutfitWearLog.user_id == user_id,
            func.coalesce(OutfitWearLog.worn_date, func.date(OutfitWearLog.worn_at)) == today,
            OutfitWearLog.deleted_at.is_(None),
        )
        .distinct()
    )
    item_ids = {str(row[0]) for row in res.all()}

    res = await session.execute(
        select(ItemWearLog.item_id)
        .where(
            ItemWearLog.user_id == user_id,
            func.coalesce(ItemWearLog.worn_date, func.date(ItemWearLog.worn_at)) == today,
            ItemWearLog.deleted_at.is_(None),
        )
        .distinct()
    )
    item_ids.update({str(row[0]) for row in res.all()})

    return {"outfits": sorted(outfit_ids), "items": sorted(item_ids)}


@router.get("/planned", response_model=WearPlannedOut)
async def wear_planned(
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    today = _today_london()
    if from_date:
        try:
            start = date.fromisoformat(from_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail="invalid_from_date") from e
    else:
        start = today
    if to_date:
        try:
            end = date.fromisoformat(to_date)
        except Exception as e:
            raise HTTPException(status_code=400, detail="invalid_to_date") from e
    else:
        end = today + timedelta(days=90)

    if end < start:
        raise HTTPException(status_code=400, detail="invalid_date_range")

    res = await session.execute(
        select(OutfitWearLog)
        .where(
            OutfitWearLog.user_id == user_id,
            OutfitWearLog.deleted_at.is_(None),
            OutfitWearLog.worn_date.is_not(None),
            OutfitWearLog.worn_date > today,
            OutfitWearLog.worn_date >= start,
            OutfitWearLog.worn_date <= end,
        )
        .order_by(OutfitWearLog.worn_date.asc())
    )
    outfit_logs = res.scalars().all()

    res = await session.execute(
        select(ItemWearLog)
        .where(
            ItemWearLog.user_id == user_id,
            ItemWearLog.deleted_at.is_(None),
            ItemWearLog.worn_date.is_not(None),
            ItemWearLog.worn_date > today,
            ItemWearLog.worn_date >= start,
            ItemWearLog.worn_date <= end,
        )
        .order_by(ItemWearLog.worn_date.asc())
    )
    item_logs = res.scalars().all()

    return WearPlannedOut(
        outfits=[
            PlannedOutfitWearOut(
                id=str(l.id),
                outfit_id=str(l.outfit_id),
                worn_date=str(l.worn_date),
                source=l.source,
                created_at=str(l.created_at) if l.created_at else None,
                notes=l.notes,
                event=l.event,
                mood=l.mood,
                season=l.season,
            )
            for l in outfit_logs
        ],
        items=[
            PlannedItemWearOut(
                id=str(l.id),
                item_id=str(l.item_id),
                worn_date=str(l.worn_date),
                source=l.source,
                created_at=str(l.created_at) if l.created_at else None,
                notes=None,
            )
            for l in item_logs
        ],
    )
