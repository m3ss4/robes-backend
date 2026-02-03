"""
Tests for onepiece (dress/jumpsuit) counting as both top and bottom
in completeness and balance scoring.
"""
import pytest
import httpx
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


class TestOnepieceCompleteness:
    """Test that onepiece items count toward top and bottom completeness."""

    @pytest.mark.asyncio
    async def test_onepiece_covers_top_and_bottom(self, client: httpx.AsyncClient):
        """
        A wardrobe with onepiece + footwear + outerwear should have 4/4 completeness
        (onepiece covers both top AND bottom).
        """
        # Create onepiece, footwear, outerwear
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Summer Dress"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Sandals"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Cardigan"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should have 4/4 core categories (onepiece counts as top + bottom)
        why = data["current"]["completeness"]["why"]
        assert "4/4" in why
        assert "onepiece" in why.lower()

    @pytest.mark.asyncio
    async def test_onepiece_only_wardrobe_not_missing_top_bottom(
        self, client: httpx.AsyncClient
    ):
        """
        A wardrobe with only onepieces should NOT report missing top or bottom.
        """
        # Create only onepieces
        for i in range(3):
            await client.post("/v1/items", json={"kind": "onepiece", "name": f"Dress{i}"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should NOT say missing top or bottom
        why = data["current"]["completeness"]["why"].lower()
        # May say missing footwear or outerwear, but not top/bottom
        if "missing" in why:
            assert "top" not in why.split("missing")[1].split(".")[0]
            assert "bottom" not in why.split("missing")[1].split(".")[0]

    @pytest.mark.asyncio
    async def test_onepiece_contributes_to_variety(self, client: httpx.AsyncClient):
        """
        Multiple onepieces should contribute to variety score for both top and bottom.
        """
        # Create 3 onepieces + footwear + outerwear for complete wardrobe
        for i in range(3):
            await client.post("/v1/items", json={"kind": "onepiece", "name": f"Dress{i}"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Completeness should be high (3 onepieces = good variety for top+bottom)
        assert data["current"]["completeness"]["score"] >= 70

    @pytest.mark.asyncio
    async def test_mixed_tops_bottoms_and_onepiece(self, client: httpx.AsyncClient):
        """
        Mix of regular tops, bottoms, AND onepieces should all contribute.
        """
        # 2 tops + 2 bottoms + 2 onepieces + footwear + outerwear
        await client.post("/v1/items", json={"kind": "top", "name": "Shirt1"})
        await client.post("/v1/items", json={"kind": "top", "name": "Shirt2"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Pants1"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Pants2"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress1"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress2"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should have good completeness
        # Effective tops = 2 + 2 = 4, effective bottoms = 2 + 2 = 4
        assert data["current"]["completeness"]["score"] >= 70
        assert "onepiece" in data["current"]["completeness"]["why"].lower()


class TestOnepieceBalance:
    """Test that onepiece items count toward top and bottom in balance scoring."""

    @pytest.mark.asyncio
    async def test_onepiece_balances_ratio(self, client: httpx.AsyncClient):
        """
        Onepieces should contribute to both tops and bottoms count in ratio.
        """
        # 2 onepieces = effectively 2 tops + 2 bottoms (1:1 ratio)
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress1"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress2"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes1"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes2"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Balance should show 2:2 ratio (from onepieces)
        why = data["current"]["balance"]["why"]
        assert "2:2" in why
        assert "onepiece" in why.lower()

    @pytest.mark.asyncio
    async def test_onepiece_helps_imbalanced_wardrobe(self, client: httpx.AsyncClient):
        """
        Adding onepieces to an imbalanced wardrobe (too many tops) should help balance.
        """
        # Start with 4 tops and 1 bottom (imbalanced)
        for i in range(4):
            await client.post("/v1/items", json={"kind": "top", "name": f"Top{i}"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Bottom1"})

        resp1 = await client.get("/v1/quality/summary?refresh=true")
        balance_before = resp1.json()["current"]["balance"]["score"]

        # Add 2 onepieces (adds 2 to both tops AND bottoms)
        # New effective: tops = 4+2=6, bottoms = 1+2=3, ratio = 2:1 (better)
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress1"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress2"})

        resp2 = await client.get("/v1/quality/summary?refresh=true")
        balance_after = resp2.json()["current"]["balance"]["score"]

        # Balance should improve (or at least not get worse)
        # The ratio went from 4:1 to 6:3 (2:1) which is within ideal range
        assert balance_after >= balance_before

    @pytest.mark.asyncio
    async def test_onepiece_only_shows_balanced_ratio(self, client: httpx.AsyncClient):
        """
        Wardrobe with only onepieces should show 1:1 ratio (always balanced).
        """
        # 3 onepieces = 3:3 ratio
        for i in range(3):
            await client.post("/v1/items", json={"kind": "onepiece", "name": f"Dress{i}"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should show 3:3 ratio
        why = data["current"]["balance"]["why"]
        assert "3:3" in why


class TestOnepieceSuggestions:
    """Test that suggestions correctly account for onepieces."""

    @pytest.mark.asyncio
    async def test_no_add_top_suggestion_when_onepiece_covers(
        self, client: httpx.AsyncClient
    ):
        """
        Should NOT suggest adding tops when onepieces provide top coverage.
        """
        # Onepiece + footwear (missing outerwear only)
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})

        await client.get("/v1/quality/summary?refresh=true")
        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        # Should NOT suggest adding top or bottom
        for sug in data["suggestions"]:
            title_lower = sug["title"].lower()
            if sug["dimension"] == "completeness":
                assert "add top" not in title_lower
                assert "add bottom" not in title_lower

    @pytest.mark.asyncio
    async def test_no_imbalance_suggestion_with_onepieces(
        self, client: httpx.AsyncClient
    ):
        """
        Should NOT suggest adding bottoms when onepieces balance the ratio.
        """
        # 2 tops + 2 onepieces = effective 4 tops, 2 bottoms
        # Wait, that's still 2:1 which is in ideal range
        await client.post("/v1/items", json={"kind": "top", "name": "Top1"})
        await client.post("/v1/items", json={"kind": "top", "name": "Top2"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress1"})
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress2"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})

        await client.get("/v1/quality/summary?refresh=true")
        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        # Should NOT have imbalance suggestion (4:2 = 2:1 ratio is ideal)
        balance_suggestions = [s for s in data["suggestions"] if s["dimension"] == "balance"]
        for sug in balance_suggestions:
            # If there's a balance suggestion, it shouldn't be about tops/bottoms imbalance
            assert "imbalanced" not in sug.get("why", "").lower() or "tops" not in sug["title"].lower()


class TestOnepieceEdgeCases:
    """Edge cases for onepiece handling."""

    @pytest.mark.asyncio
    async def test_zero_onepieces_no_change(self, client: httpx.AsyncClient):
        """
        When there are no onepieces, behavior should be unchanged from before.
        """
        # Standard wardrobe without onepieces
        await client.post("/v1/items", json={"kind": "top", "name": "Top1"})
        await client.post("/v1/items", json={"kind": "top", "name": "Top2"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Bottom1"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should NOT mention onepiece in the why text
        assert "onepiece" not in data["current"]["completeness"]["why"].lower()
        assert "onepiece" not in data["current"]["balance"]["why"].lower()

        # Should show actual counts (2:1 for tops:bottoms)
        assert "2:1" in data["current"]["balance"]["why"]

    @pytest.mark.asyncio
    async def test_single_onepiece_minimum_viable(self, client: httpx.AsyncClient):
        """
        Single onepiece + footwear + outerwear = complete wardrobe.
        Balance requires 5+ items to calculate ratio.
        """
        await client.post("/v1/items", json={"kind": "onepiece", "name": "Dress"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Sneakers"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Coat"})

        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Should have 4/4 core categories
        assert "4/4" in data["current"]["completeness"]["why"]

        # Balance shows 1:1 ratio (onepiece counts as 1 top and 1 bottom)
        assert "1:1" in data["current"]["balance"]["why"]
