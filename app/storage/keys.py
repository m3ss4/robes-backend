import uuid


def original_key(user_id: str, item_id: str, ext: str = "jpg") -> str:
    return f"u/{user_id}/items/{item_id}/{uuid.uuid4().hex}_orig.{ext}"
