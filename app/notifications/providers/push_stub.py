from app.notifications.types import Notification


class PushNotificationProvider:
    def send(self, _notification: Notification) -> None:
        return None
