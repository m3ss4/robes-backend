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
        await session.execute(text("TRUNCATE item_suggestion_audit RESTART IDENTITY CASCADE"))
        await session.execute(text("TRUNCATE item RESTART IDENTITY CASCADE"))
        await session.commit()
        break

@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url=API_BASE) as ac:
            yield ac

@pytest.mark.asyncio
async def test_suggest_attributes_rule_only(client: httpx.AsyncClient):
    resp = await client.post("/v1/items/suggest-attributes", json={"hints": {"category": "top", "base_color": "navy"}})
    assert resp.status_code == 200
    draft = resp.json()["draft"]
    assert draft["category"]["value"] == "top"
    assert draft["base_color"]["value"] == "navy"
    assert draft["pattern"]["value"] == "solid"
    assert draft["category"]["confidence"] >= 0.6

@pytest.mark.asyncio
async def test_suggest_attributes_with_lock_fields(client: httpx.AsyncClient):
    resp = await client.post(
        "/v1/items/suggest-attributes",
        json={"hints": {"base_color": "red"}, "lock_fields": ["base_color"]},
    )
    assert resp.status_code == 200
    draft = resp.json()["draft"]
    assert draft["base_color"]["value"] == "red"
    assert draft["base_color"]["source"] == "locked"
