from typing import List
from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: str | None = None
    title: str | None = None
    body: str | None = None


class NotificationsOut(BaseModel):
    items: List[NotificationOut]
