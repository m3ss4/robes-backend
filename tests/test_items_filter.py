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

async def _make_items(client: httpx.AsyncClient):
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["minimal"], "event_tags": ["office"], "season_tags": ["autumn"]})
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["streetwear"], "event_tags": ["casual"], "season_tags": ["summer"]})
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["minimal"], "event_tags": ["casual"]})

@pytest.mark.asyncio
async def test_filter_and_and_or(client: httpx.AsyncClient):
    await _make_items(client)

    resp = await client.get("/v1/items", params={"style": "minimal", "event": "office"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["event_tags"] == ["office"]

    resp_or = await client.get("/v1/items", params={"any_style": "streetwear"})
    assert resp_or.status_code == 200
    data_or = resp_or.json()
    assert len(data_or) == 1
    assert data_or[0]["style_tags"] == ["streetwear"]

    resp_season = await client.get("/v1/items", params={"season": "summer"})
    assert resp_season.status_code == 200
    data_season = resp_season.json()
    assert len(data_season) == 1
    assert data_season[0]["season_tags"] == ["summer"]
