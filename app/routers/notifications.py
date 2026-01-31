from fastapi import APIRouter
from app.schemas.notifications import NotificationsOut

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationsOut)
async def list_notifications():
    return NotificationsOut(items=[])
