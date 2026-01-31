import logging
from app.notifications.types import Notification


class LogNotificationProvider:
    def send(self, notification: Notification) -> None:
        logging.getLogger("notifications").info("notify %s %s", notification.user_id, notification.title)
