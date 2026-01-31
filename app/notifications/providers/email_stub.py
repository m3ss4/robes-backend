from app.notifications.types import Notification


class EmailNotificationProvider:
    def send(self, _notification: Notification) -> None:
        return None
