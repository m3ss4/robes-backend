import os
from app.notifications.config import NotificationsConfig
from app.notifications.providers.log_only import LogNotificationProvider
from app.notifications.providers.email_stub import EmailNotificationProvider
from app.notifications.providers.push_stub import PushNotificationProvider
from app.notifications.types import Notification


class NotificationService:
    def __init__(self, config: NotificationsConfig | None = None) -> None:
        self.config = config or NotificationsConfig(provider=os.getenv("NOTIFY_PROVIDER", "log"))
        if self.config.provider == "email":
            self.provider = EmailNotificationProvider()
        elif self.config.provider == "push":
            self.provider = PushNotificationProvider()
        else:
            self.provider = LogNotificationProvider()

    def send(self, notification: Notification) -> None:
        self.provider.send(notification)
