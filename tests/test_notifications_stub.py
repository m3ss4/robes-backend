from app.services.notifications.service import NotificationService
from app.notifications.types import Notification


def test_notifications_send_noop():
    service = NotificationService()
    service.send(Notification(user_id="u", title="t", body="b"))
