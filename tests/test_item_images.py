import pytest
import httpx
from sqlalchemy import text
from asgi_lifespan import LifespanManager

from app.main import app
from app.core.db import get_session

API_BASE = "http://test"

@pytest.fixture(autouse=True)
async def clean_db():
    async for session in get_session():
        await session.execute(text("TRUNCATE item_image RESTART IDENTITY CASCADE"))
        await session.execute(text("TRUNCATE item RESTART IDENTITY CASCADE"))
        await session.commit()
        break

@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url=API_BASE) as ac:
            yield ac

@pytest.mark.asyncio
async def test_create_item_with_images(client: httpx.AsyncClient):
    payload = {
        "kind": "top",
        "images": [{"url": "http://example.com/a.jpg"}, {"url": "http://example.com/b.jpg", "view": "back"}],
    }
    resp = await client.post("/v1/items", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["images"]) == 2
    assert data["images"][0]["view"] == "front"
    assert data["images"][1]["view"] == "back"

@pytest.mark.asyncio
async def test_add_item_images_endpoint(client: httpx.AsyncClient):
    create = await client.post("/v1/items", json={"kind": "top"})
    item_id = create.json()["id"]
    resp = await client.post(
        f"/v1/items/{item_id}/images",
        json=[{"url": "http://example.com/c.jpg", "view": "side"}],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["view"] == "side"

@pytest.mark.asyncio
async def test_invalid_view_rejected(client: httpx.AsyncClient):
    create = await client.post("/v1/items", json={"kind": "top"})
    item_id = create.json()["id"]
    resp = await client.post(
        f"/v1/items/{item_id}/images",
        json=[{"url": "http://example.com/c.jpg", "view": "weird"}],
    )
    assert resp.status_code == 400
