from typing import Protocol
from app.notifications.types import Notification


class NotificationProvider(Protocol):
    def send(self, notification: Notification) -> None:
        ...
