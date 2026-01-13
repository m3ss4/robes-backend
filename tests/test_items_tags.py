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
async def test_create_item_normalizes_tags(client: httpx.AsyncClient):
    payload = {
        "kind": "top",
        "type": "Shirt",
        "name": "Navy Tee",
        "style_tags": ["Minimal  ", "Street Wear"],
        "event_tags": ["Office"],
        "season_tags": ["Winter"],
        "base_color": "Navy",
    }
    resp = await client.post("/v1/items", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "shirt"
    assert data["base_color"] == "navy"
    assert data["style_tags"] == ["minimal", "street-wear"]
    assert data["event_tags"] == ["office"]
    assert data["season_tags"] == ["winter"]

@pytest.mark.asyncio
async def test_create_item_rejects_excess_tags(client: httpx.AsyncClient):
    payload = {
        "kind": "top",
        "style_tags": [f"tag{i}" for i in range(11)],
    }
    resp = await client.post("/v1/items", json=payload)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "invalid_tag"
    assert detail["details"]["category"] == "style"
    assert detail["details"]["reason"] == "too_many_tags"

@pytest.mark.asyncio
async def test_patch_add_remove_tags(client: httpx.AsyncClient):
    create = await client.post("/v1/items", json={"kind": "top", "style_tags": ["minimal"]})
    item_id = create.json()["id"]

    add_resp = await client.patch(
        f"/v1/items/{item_id}/tags",
        json={"op": "add", "style_tags": ["classic"], "event_tags": ["Office"]},
    )
    assert add_resp.status_code == 200
    data = add_resp.json()
    assert set(data["style_tags"]) == {"minimal", "classic"}
    assert data["event_tags"] == ["office"]

    remove_resp = await client.patch(
        f"/v1/items/{item_id}/tags",
        json={"op": "remove", "style_tags": ["minimal"]},
    )
    assert remove_resp.status_code == 200
    data = remove_resp.json()
    assert data["style_tags"] == ["classic"]

@pytest.mark.asyncio
async def test_patch_rejects_invalid_season(client: httpx.AsyncClient):
    create = await client.post("/v1/items", json={"kind": "top"})
    item_id = create.json()["id"]
    resp = await client.patch(
        f"/v1/items/{item_id}/tags",
        json={"op": "set", "season_tags": ["monsoon"]},
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["details"]["category"] == "season"
    assert detail["details"]["reason"] == "not_in_enum"
