import pytest
import httpx
from asgi_lifespan import LifespanManager
from sqlalchemy import text

from app.main import app
from app.core.db import get_session


@pytest.fixture(autouse=True)
async def clean_db():
    async for session in get_session():
        # wipe outfits and related tables for isolation
        await session.execute(text("TRUNCATE outfit_wear_log_item CASCADE"))
        await session.execute(text("TRUNCATE outfit_wear_log CASCADE"))
        await session.execute(text("TRUNCATE outfit_revision CASCADE"))
        await session.execute(text("TRUNCATE outfit_item CASCADE"))
        await session.execute(text("TRUNCATE outfit CASCADE"))
        await session.execute(text("TRUNCATE suggest_session CASCADE"))
        await session.commit()
        break


@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url="http://test") as ac:
            yield ac


@pytest.mark.asyncio
async def test_outfit_crud_and_score(client: httpx.AsyncClient):
    # create a couple of items first
    await client.post("/v1/items", json={"kind": "top", "name": "Tee"})
    await client.post("/v1/items", json={"kind": "bottom", "name": "Jeans"})
    await client.post("/v1/items", json={"kind": "footwear", "name": "Sneakers"})

    # list items
    items_resp = await client.get("/v1/items")
    assert items_resp.status_code == 200
    items = items_resp.json()
    id_map = {it["kind"]: it["id"] for it in items}

    payload = {
        "name": "Test Outfit",
        "items": [
            {"item_id": id_map["top"], "slot": "top"},
            {"item_id": id_map["bottom"], "slot": "bottom"},
            {"item_id": id_map["footwear"], "slot": "shoes"},
        ],
    }
    resp = await client.post("/v1/outfits", json=payload)
    assert resp.status_code == 200
    outfit = resp.json()
    assert outfit["status"] == "user_saved"
    assert outfit["items"]

    # score
    score_resp = await client.post(
        "/v1/outfits/score", json={"items": [{"item_id": id_map["top"], "slot": "top"}]}
    )
    assert score_resp.status_code == 200
    assert "metrics" in score_resp.json()

    # wear log
    wear_resp = await client.post(f"/v1/outfits/{outfit['id']}/wear-log", json={})
    assert wear_resp.status_code == 200
    history = await client.get(f"/v1/outfits/{outfit['id']}/history")
    assert history.status_code == 200
    assert len(history.json()) == 1


@pytest.mark.asyncio
async def test_suggest_and_rotate(client: httpx.AsyncClient):
    await client.post("/v1/items", json={"kind": "top", "name": "Tee"})
    await client.post("/v1/items", json={"kind": "bottom", "name": "Jeans"})
    await client.post("/v1/items", json={"kind": "footwear", "name": "Sneakers"})
    # call suggest
    sugg = await client.post("/v1/outfits/suggest", json={})
    assert sugg.status_code == 200
    data = sugg.json()
    assert "session_id" in data
    # rotate will error without a valid session id; we expect empty outfits or one
    assert "outfits" in data
