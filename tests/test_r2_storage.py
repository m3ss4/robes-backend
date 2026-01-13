import os
import pytest

from app.storage.r2 import object_url, presign_put, presign_get


class DummyS3:
    def __init__(self):
        self.last_params = None

    def generate_presigned_url(self, op, Params, ExpiresIn):
        self.last_params = (op, Params, ExpiresIn)
        return f"https://example.com/{Params['Bucket']}/{Params['Key']}?signature=dummy"


@pytest.mark.asyncio
async def test_object_url_prefers_cdn(monkeypatch):
    monkeypatch.setenv("R2_CDN_BASE", "https://cdn.example.com")
    monkeypatch.setenv("R2_ENDPOINT", "https://r2.example.com")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    from importlib import reload
    import app.storage.r2 as r2

    reload(r2)
    assert r2.object_url("k1") == "https://cdn.example.com/k1"
    monkeypatch.setenv("R2_CDN_BASE", "")
    reload(r2)
    assert r2.object_url("k1") == "https://r2.example.com/bucket/k1"


@pytest.mark.asyncio
async def test_presign_put(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "bucket")
    import app.storage.r2 as r2

    dummy = DummyS3()
    monkeypatch.setattr(r2, "r2_client", lambda: dummy)
    url, headers = presign_put("key1", "image/jpeg", expires=100)
    assert "bucket/key1" in url
    assert headers["Content-Type"] == "image/jpeg"
    assert dummy.last_params[0] == "put_object"
    assert dummy.last_params[1]["Bucket"] == "bucket"
    assert dummy.last_params[1]["Key"] == "key1"


@pytest.mark.asyncio
async def test_presign_get(monkeypatch):
    monkeypatch.setenv("R2_BUCKET", "bucket")
    import app.storage.r2 as r2

    dummy = DummyS3()
    monkeypatch.setattr(r2, "r2_client", lambda: dummy)
    url = presign_get("key2", expires=50, bucket="bucket")
    assert "bucket/key2" in url
    assert dummy.last_params[0] == "get_object"
    assert dummy.last_params[1]["Key"] == "key2"
