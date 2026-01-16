from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.deps import get_current_user_id
from app.core.db import get_session
from app.models.models import OutfitWearLog, OutfitWearLogItem, ItemWearLog

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
            OutfitWearLog.worn_date == today,
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
            OutfitWearLog.worn_date == today,
            OutfitWearLog.deleted_at.is_(None),
        )
        .distinct()
    )
    item_ids = {str(row[0]) for row in res.all()}

    res = await session.execute(
        select(ItemWearLog.item_id)
        .where(
            ItemWearLog.user_id == user_id,
            ItemWearLog.worn_date == today,
            ItemWearLog.deleted_at.is_(None),
        )
        .distinct()
    )
    item_ids.update({str(row[0]) for row in res.all()})

    return {"outfits": sorted(outfit_ids), "items": sorted(item_ids)}
