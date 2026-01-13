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
async def test_taxonomy_endpoint(client: httpx.AsyncClient):
    resp = await client.get("/v1/taxonomy")
    assert resp.status_code == 200
    data = resp.json()
    assert "facets" in data
    assert "category" in data["facets"]
    assert "type" in data["facets"]

@pytest.mark.asyncio
async def test_tag_suggest_endpoint(client: httpx.AsyncClient):
    # seed history
    await client.post("/v1/items", json={"kind": "top", "style_tags": ["minimal"]})
    resp = await client.get("/v1/tags/suggest", params={"category": "style", "q": "min"})
    assert resp.status_code == 200
    data = resp.json()["suggestions"]
    assert any(s["key"] == "minimal" for s in data)
