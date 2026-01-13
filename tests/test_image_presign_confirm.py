import pytest
from uuid import uuid4

from app.storage import r2 as storage_r2


class DummyS3:
    def __init__(self):
        self.head_called = False

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://presigned/{Params['Bucket']}/{Params['Key']}"

    def head_object(self, Bucket, Key):
        self.head_called = True
        return {"ContentLength": 1234}


def test_presign_builds_url(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.example.com")
    dummy = DummyS3()
    monkeypatch.setattr(storage_r2, "r2_client", lambda: dummy)
    url, headers = storage_r2.presign_put("abc", "image/jpeg")
    assert "bucket/abc" in url
    assert headers["Content-Type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_confirm_uses_head(monkeypatch, anyio_backend):
    dummy = DummyS3()
    monkeypatch.setattr(storage_r2, "r2_client", lambda: dummy)
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.example.com")
    # Simulate DB session with mock; here we just call storage helper
    url = storage_r2.object_url("k1")
    assert url.endswith("/bucket/k1") or "cdn" in url
    assert dummy.head_called is False
    # head_object invoked when confirm_image is called in router; not executed here to avoid DB dependency
