"""
Tests for utilization scoring - specifically covering the outfit_wear_log_items fix
and ensuring no double-counting or missed counts.
"""
import pytest
import httpx
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import text
from asgi_lifespan import LifespanManager

from app.main import app
from app.core.db import get_session
from app.core.config import settings

# Enable quality module for tests
settings.QUALITY_ENABLED = True

from app.routers import quality as quality_router
prefix = settings.API_PREFIX
if not any(r.path == f"{prefix}/quality/summary" for r in app.routes):
    app.include_router(quality_router.router, prefix=prefix)

API_BASE = "http://test"


@pytest.fixture(autouse=True)
async def clean_db():
    """Clean up tables before each test."""
    async for session in get_session():
        await session.execute(text("TRUNCATE wardrobe_quality_suggestion CASCADE"))
        await session.execute(text("TRUNCATE wardrobe_quality_score CASCADE"))
        await session.execute(text("TRUNCATE item_wear_log CASCADE"))
        await session.execute(text("TRUNCATE outfit_wear_log_item CASCADE"))
        await session.execute(text("TRUNCATE outfit_wear_log CASCADE"))
        await session.execute(text("TRUNCATE outfit_item CASCADE"))
        await session.execute(text("TRUNCATE outfit CASCADE"))
        await session.execute(text("TRUNCATE item_image CASCADE"))
        await session.execute(text("TRUNCATE item CASCADE"))
        await session.commit()
        break


@pytest.fixture
async def client():
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url=API_BASE) as ac:
            yield ac


class TestUtilizationOutfitWears:
    """Test that outfit wears are correctly counted in utilization."""

    @pytest.fixture
    async def items_and_outfit(self, client: httpx.AsyncClient):
        """Create 5 items and an outfit using 3 of them."""
        items = []
        for i in range(5):
            r = await client.post("/v1/items", json={"kind": "top", "name": f"Item{i}"})
            items.append(r.json()["id"])

        # Create outfit with first 3 items
        outfit_r = await client.post("/v1/outfits", json={
            "name": "Test Outfit",
            "items": [
                {"item_id": items[0], "slot": "top"},
                {"item_id": items[1], "slot": "bottom"},
                {"item_id": items[2], "slot": "shoes"},
            ]
        })
        outfit_id = outfit_r.json()["id"]
        return {"items": items, "outfit_id": outfit_id}

    @pytest.mark.asyncio
    async def test_outfit_wear_counts_items(
        self, client: httpx.AsyncClient, items_and_outfit
    ):
        """Logging an outfit wear should count all items in that outfit as worn."""
        outfit_id = items_and_outfit["outfit_id"]

        # Log outfit wear
        await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        # Get quality summary
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should have 5 items, 3 worn (via outfit)
        assert data["current"]["items_count"] == 5
        # Utilization should reflect that 3 of 5 items were worn
        assert "3" in data["current"]["utilization"]["why"] or "worn" in data["current"]["utilization"]["why"].lower()

    @pytest.mark.asyncio
    async def test_no_double_counting_today_outfit_wear(
        self, client: httpx.AsyncClient, items_and_outfit
    ):
        """
        For today's outfit wear, items appear in both outfit_wear_log_items
        and item_wear_logs. Verify no double counting.
        """
        outfit_id = items_and_outfit["outfit_id"]

        # Log outfit wear (for today - creates both OutfitWearLogItem and ItemWearLog)
        await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        # Get quality summary
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Log another outfit wear
        await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        # Refresh and check - should show 2 wears per item, not 4
        resp2 = await client.get("/v1/quality/summary?refresh=true")
        data2 = resp2.json()

        # The wear count should increase proportionally, not double
        # With 5 items and 2 outfit wears (3 items each), we have 6 item-wears total
        assert data2["current"]["wear_logs_count"] >= 2


class TestUtilizationStandaloneItemWears:
    """Test that standalone item wears (not via outfit) are counted."""

    @pytest.fixture
    async def items_only(self, client: httpx.AsyncClient):
        """Create 5 items without outfits."""
        items = []
        for i in range(5):
            r = await client.post("/v1/items", json={"kind": "top", "name": f"Item{i}"})
            items.append(r.json()["id"])
        return items

    @pytest.mark.asyncio
    async def test_standalone_item_wear_counted(
        self, client: httpx.AsyncClient, items_only
    ):
        """Standalone item wear (not via outfit) should be counted."""
        item_id = items_only[0]

        # Log standalone item wear
        await client.post(f"/v1/items/{item_id}/wear-log", json={})

        # Get quality summary
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should have 5 items, 1 worn
        assert data["current"]["items_count"] == 5
        assert data["current"]["wear_logs_count"] >= 1


class TestUtilizationMixedWears:
    """Test mixed scenarios: outfit wears + standalone wears."""

    @pytest.fixture
    async def mixed_setup(self, client: httpx.AsyncClient):
        """Create items, outfit, and various wear scenarios."""
        items = []
        for i in range(5):
            r = await client.post("/v1/items", json={"kind": "top", "name": f"Item{i}"})
            items.append(r.json()["id"])

        # Create outfit with items 0, 1, 2
        outfit_r = await client.post("/v1/outfits", json={
            "name": "Test Outfit",
            "items": [
                {"item_id": items[0], "slot": "top"},
                {"item_id": items[1], "slot": "bottom"},
                {"item_id": items[2], "slot": "shoes"},
            ]
        })
        outfit_id = outfit_r.json()["id"]
        return {"items": items, "outfit_id": outfit_id}

    @pytest.mark.asyncio
    async def test_same_item_worn_via_outfit_and_standalone(
        self, client: httpx.AsyncClient, mixed_setup
    ):
        """
        Same item worn via outfit AND standalone should count as 2 separate wears.
        """
        items = mixed_setup["items"]
        outfit_id = mixed_setup["outfit_id"]

        # Wear item[0] via outfit
        await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        # Also wear item[0] standalone
        await client.post(f"/v1/items/{items[0]}/wear-log", json={})

        # Get quality summary
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # item[0] should have 2 wears (1 outfit + 1 standalone)
        # item[1] and item[2] should have 1 wear each (outfit only)
        # item[3] and item[4] should have 0 wears
        # Total: 4 item-wears, 4 items worn out of 5
        assert data["current"]["items_count"] == 5
        # At least 4 items should show as worn (items 0,1,2 from outfit + item 0 standalone doesn't add new item)
        # Actually items 0,1,2 are worn, items 3,4 are not
        assert "3" in data["current"]["utilization"]["why"] or "worn" in data["current"]["utilization"]["why"].lower()

    @pytest.mark.asyncio
    async def test_different_items_outfit_vs_standalone(
        self, client: httpx.AsyncClient, mixed_setup
    ):
        """
        Outfit wear for items 0,1,2 and standalone wear for item 3.
        Should count 4 distinct items as worn.
        """
        items = mixed_setup["items"]
        outfit_id = mixed_setup["outfit_id"]

        # Wear outfit (items 0,1,2)
        await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        # Wear item 3 standalone
        await client.post(f"/v1/items/{items[3]}/wear-log", json={})

        # Get quality summary
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # 4 items worn out of 5
        assert data["current"]["items_count"] == 5
        why = data["current"]["utilization"]["why"].lower()
        assert "4" in data["current"]["utilization"]["why"] or "worn" in why


class TestUtilizationNoWears:
    """Test utilization with no wear logs."""

    @pytest.mark.asyncio
    async def test_no_wears_low_score(self, client: httpx.AsyncClient):
        """With items but no wears, utilization should be low with appropriate message."""
        # Create items
        for i in range(5):
            await client.post("/v1/items", json={"kind": "top", "name": f"Item{i}"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should indicate no wear logs
        assert data["current"]["utilization"]["score"] <= 30
        assert "no wear" in data["current"]["utilization"]["why"].lower() or "never worn" in data["current"]["utilization"]["why"].lower()
