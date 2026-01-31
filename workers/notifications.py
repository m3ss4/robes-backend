from app.services.notifications.dispatcher import dispatch
from app.notifications.types import Notification


def send_preview(user_id: str, title: str, body: str) -> None:
    dispatch(Notification(user_id=user_id, title=title, body=body))
