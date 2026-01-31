from app.notifications.types import Notification
from app.services.notifications.service import NotificationService


def dispatch(notification: Notification) -> None:
    NotificationService().send(notification)
