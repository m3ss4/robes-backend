"""
Benchmark tests for quality scoring performance.
These tests ensure scoring completes in reasonable time.
"""
import pytest
import httpx
import time
from sqlalchemy import text
from asgi_lifespan import LifespanManager

from app.main import app
from app.core.db import get_session
from app.core.config import settings

# Enable quality module for tests
settings.QUALITY_ENABLED = True

# Re-register router since we're enabling it after import
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


class TestScoringPerformance:
    """Benchmark tests for scoring performance."""

    @pytest.fixture
    async def large_wardrobe(self, client: httpx.AsyncClient):
        """Create a larger wardrobe for performance testing."""
        items = []
        # 50 tops
        for i in range(50):
            r = await client.post("/v1/items", json={
                "kind": "top",
                "name": f"Top{i}",
                "base_color": ["white", "black", "blue", "gray", "navy"][i % 5],
                "style_tags": [["casual"], ["formal"], ["sporty"]][i % 3],
                "season_tags": [["spring", "summer"], ["autumn", "winter"]][i % 2],
            })
            assert r.status_code == 200 or r.status_code == 201, f"Failed to create item: {r.status_code} - {r.text}"
            items.append(r.json()["id"])

        # 30 bottoms
        for i in range(30):
            r = await client.post("/v1/items", json={
                "kind": "bottom",
                "name": f"Bottom{i}",
                "base_color": ["black", "blue", "beige"][i % 3],
            })
            assert r.status_code == 200 or r.status_code == 201, f"Failed to create bottom: {r.status_code} - {r.text}"
            items.append(r.json()["id"])

        # 10 footwear
        for i in range(10):
            r = await client.post("/v1/items", json={
                "kind": "footwear",
                "name": f"Shoes{i}",
            })
            assert r.status_code == 200 or r.status_code == 201, f"Failed to create footwear: {r.status_code} - {r.text}"
            items.append(r.json()["id"])

        # 10 outerwear
        for i in range(10):
            r = await client.post("/v1/items", json={
                "kind": "outerwear",
                "name": f"Jacket{i}",
            })
            assert r.status_code == 200 or r.status_code == 201, f"Failed to create outerwear: {r.status_code} - {r.text}"
            items.append(r.json()["id"])

        # Create 20 outfits
        for i in range(20):
            await client.post("/v1/outfits", json={
                "name": f"Outfit{i}",
                "items": [
                    {"item_id": items[i % 50], "slot": "top"},
                    {"item_id": items[50 + (i % 30)], "slot": "bottom"},
                    {"item_id": items[80 + (i % 10)], "slot": "shoes"},
                ]
            })

        return items

    @pytest.mark.asyncio
    async def test_scoring_completes_in_reasonable_time(
        self, client: httpx.AsyncClient, large_wardrobe
    ):
        """Scoring 100 items should complete in under 2 seconds."""
        start = time.time()
        resp = await client.get("/v1/quality/summary?refresh=true")
        duration = time.time() - start

        assert resp.status_code == 200
        assert duration < 2.0, f"Scoring took {duration:.2f}s, expected < 2s"

    @pytest.mark.asyncio
    async def test_suggestions_endpoint_performance(
        self, client: httpx.AsyncClient, large_wardrobe
    ):
        """Suggestions endpoint should respond quickly."""
        # First compute score
        await client.get("/v1/quality/summary")

        start = time.time()
        resp = await client.get("/v1/quality/suggestions")
        duration = time.time() - start

        assert resp.status_code == 200
        assert duration < 0.5, f"Suggestions took {duration:.2f}s, expected < 0.5s"

    @pytest.mark.asyncio
    async def test_preferences_endpoint_performance(
        self, client: httpx.AsyncClient
    ):
        """Preferences endpoint should be very fast."""
        start = time.time()
        resp = await client.get("/v1/quality/preferences")
        duration = time.time() - start

        assert resp.status_code == 200
        assert duration < 0.1, f"Preferences took {duration:.2f}s, expected < 0.1s"


class TestScoreAccuracy:
    """Tests verifying score calculation accuracy."""

    @pytest.mark.asyncio
    async def test_completeness_increases_with_categories(
        self, client: httpx.AsyncClient
    ):
        """Completeness should increase as more categories are added."""
        scores = []

        # Empty
        resp = await client.get("/v1/quality/summary?refresh=true")
        scores.append(resp.json()["current"]["completeness"]["score"])

        # Add top
        await client.post("/v1/items", json={"kind": "top", "name": "Top"})
        resp = await client.get("/v1/quality/summary?refresh=true")
        scores.append(resp.json()["current"]["completeness"]["score"])

        # Add bottom
        await client.post("/v1/items", json={"kind": "bottom", "name": "Bottom"})
        resp = await client.get("/v1/quality/summary?refresh=true")
        scores.append(resp.json()["current"]["completeness"]["score"])

        # Add footwear
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        resp = await client.get("/v1/quality/summary?refresh=true")
        scores.append(resp.json()["current"]["completeness"]["score"])

        # Add outerwear
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})
        resp = await client.get("/v1/quality/summary?refresh=true")
        scores.append(resp.json()["current"]["completeness"]["score"])

        # Each addition should increase or maintain completeness
        for i in range(1, len(scores)):
            assert scores[i] >= scores[i-1], f"Score decreased from {scores[i-1]} to {scores[i]}"

    @pytest.mark.asyncio
    async def test_versatility_increases_with_outfits(
        self, client: httpx.AsyncClient
    ):
        """Versatility should increase as items are used in more outfits."""
        # Create base items
        items = []
        for kind in ["top", "top", "bottom", "bottom", "footwear"]:
            r = await client.post("/v1/items", json={"kind": kind, "name": f"{kind}"})
            items.append(r.json()["id"])

        # Score with no outfits
        resp = await client.get("/v1/quality/summary?refresh=true")
        score_no_outfits = resp.json()["current"]["versatility"]["score"]

        # Create outfit using some items
        await client.post("/v1/outfits", json={
            "name": "Outfit1",
            "items": [
                {"item_id": items[0], "slot": "top"},
                {"item_id": items[2], "slot": "bottom"},
                {"item_id": items[4], "slot": "shoes"},
            ]
        })

        resp = await client.get("/v1/quality/summary?refresh=true")
        score_one_outfit = resp.json()["current"]["versatility"]["score"]

        # Create another outfit using same items (reuse)
        await client.post("/v1/outfits", json={
            "name": "Outfit2",
            "items": [
                {"item_id": items[0], "slot": "top"},  # Reuse
                {"item_id": items[3], "slot": "bottom"},
                {"item_id": items[4], "slot": "shoes"},  # Reuse
            ]
        })

        resp = await client.get("/v1/quality/summary?refresh=true")
        score_two_outfits = resp.json()["current"]["versatility"]["score"]

        # Versatility should increase with more outfit combinations
        assert score_one_outfit > score_no_outfits
        assert score_two_outfits >= score_one_outfit
