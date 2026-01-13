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
        await session.execute(text("TRUNCATE item RESTART IDENTITY CASCADE"))
        await session.commit()
        break

@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url=API_BASE) as ac:
            yield ac

@pytest.mark.asyncio
async def test_builtin_suggestions(client: httpx.AsyncClient):
    resp = await client.get("/v1/tags/suggest", params={"category": "event"})
    assert resp.status_code == 200
    data = resp.json()["suggestions"]
    keys = [s["key"] for s in data]
    assert "office" in keys

@pytest.mark.asyncio
async def test_prefix_filters_and_user_history(client: httpx.AsyncClient):
    # Seed history
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["vintage", "maximalist"]})
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["vintage"]})

    resp = await client.get("/v1/tags/suggest", params={"category": "style", "q": "vin"})
    assert resp.status_code == 200
    data = resp.json()["suggestions"]
    assert any(s["key"] == "vintage" and s["source"] == "user-history" for s in data)
    assert all(s["key"].startswith("vin") for s in data)
