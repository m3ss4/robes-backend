from app.services.notifications.dispatcher import dispatch
from app.notifications.types import Notification


if __name__ == "__main__":
    dispatch(Notification(user_id="demo", title="Hello", body="World"))
    print("notification preview sent")
