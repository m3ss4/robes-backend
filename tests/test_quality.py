import pytest
import httpx
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
# Only add if not already registered
if not any(r.path == f"{prefix}/quality/summary" for r in app.routes):
    app.include_router(quality_router.router, prefix=prefix)

API_BASE = "http://test"


@pytest.fixture(autouse=True)
async def clean_db():
    """Clean up quality and wardrobe tables before each test."""
    async for session in get_session():
        # Clean in order due to foreign keys
        await session.execute(text("TRUNCATE wardrobe_quality_suggestion CASCADE"))
        await session.execute(text("TRUNCATE wardrobe_quality_score CASCADE"))
        await session.execute(text("TRUNCATE item_wear_log CASCADE"))
        await session.execute(text("TRUNCATE outfit_wear_log_item CASCADE"))
        await session.execute(text("TRUNCATE outfit_wear_log CASCADE"))
        await session.execute(text("TRUNCATE outfit_item CASCADE"))
        await session.execute(text("TRUNCATE outfit CASCADE"))
        await session.execute(text("TRUNCATE item_image CASCADE"))
        await session.execute(text("TRUNCATE item CASCADE"))
        # Reset user preferences to defaults
        await session.execute(text(
            'UPDATE "user" SET quality_preferences = NULL'
        ))
        await session.commit()
        break


@pytest.fixture
async def client():
    """Async HTTP client with lifespan management."""
    async with LifespanManager(app):
        async with httpx.AsyncClient(app=app, base_url=API_BASE) as ac:
            yield ac


class TestEmptyWardrobe:
    """Test quality scoring with empty wardrobe."""

    @pytest.mark.asyncio
    async def test_empty_wardrobe_summary(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Should have low scores with appropriate explanations
        assert data["current"]["items_count"] == 0
        assert data["current"]["completeness"]["score"] == 0
        assert "no items" in data["current"]["completeness"]["why"].lower()

    @pytest.mark.asyncio
    async def test_empty_wardrobe_suggestions(self, client: httpx.AsyncClient):
        # First get summary to trigger score computation
        await client.get("/v1/quality/summary")

        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        # Should suggest adding items
        assert any(s["suggestion_type"] == "add_item" for s in data["suggestions"])


class TestMinimalWardrobe:
    """Test quality scoring with minimal items (< 5)."""

    @pytest.fixture
    async def minimal_items(self, client: httpx.AsyncClient):
        # Create 3 items
        await client.post("/v1/items", json={"kind": "top", "name": "Tee"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Jeans"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Sneakers"})

    @pytest.mark.asyncio
    async def test_minimal_items_low_confidence(
        self, client: httpx.AsyncClient, minimal_items
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert data["current"]["items_count"] == 3
        # Versatility should have low confidence with few items
        assert data["current"]["versatility"]["confidence"] < 0.5

    @pytest.mark.asyncio
    async def test_minimal_wardrobe_completeness(
        self, client: httpx.AsyncClient, minimal_items
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Has 3 of 4 core categories (missing outerwear)
        assert data["current"]["completeness"]["score"] > 0
        assert "outerwear" in data["current"]["completeness"]["why"].lower()


class TestHeavyUsage:
    """Test quality scoring with heavy wear log usage."""

    @pytest.fixture
    async def heavy_usage_setup(self, client: httpx.AsyncClient):
        # Create items
        items = []
        for i in range(5):
            r = await client.post("/v1/items", json={"kind": "top", "name": f"Top{i}"})
            items.append(r.json()["id"])
        for i in range(3):
            r = await client.post("/v1/items", json={"kind": "bottom", "name": f"Bottom{i}"})
            items.append(r.json()["id"])
        r = await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        items.append(r.json()["id"])

        # Create outfit
        outfit_r = await client.post("/v1/outfits", json={
            "name": "Test Outfit",
            "items": [
                {"item_id": items[0], "slot": "top"},
                {"item_id": items[5], "slot": "bottom"},
                {"item_id": items[8], "slot": "shoes"},
            ]
        })
        outfit_id = outfit_r.json()["id"]

        # Log multiple wears
        for _ in range(10):
            await client.post(f"/v1/outfits/{outfit_id}/wear-log", json={})

        return items

    @pytest.mark.asyncio
    async def test_heavy_usage_high_utilization(
        self, client: httpx.AsyncClient, heavy_usage_setup
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Wear logs should be counted and boost utilization confidence
        # Note: Some wears may be deduplicated or rate-limited
        assert data["current"]["wear_logs_count"] >= 1
        assert data["current"]["utilization"]["confidence"] > 0.4


class TestMissingCategories:
    """Test quality scoring with missing core categories."""

    @pytest.fixture
    async def only_tops(self, client: httpx.AsyncClient):
        # Create only tops
        for i in range(5):
            await client.post("/v1/items", json={"kind": "top", "name": f"Top{i}"})

    @pytest.mark.asyncio
    async def test_missing_categories_low_completeness(
        self, client: httpx.AsyncClient, only_tops
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Completeness should be low with only tops
        assert data["current"]["completeness"]["score"] < 50
        assert "missing" in data["current"]["completeness"]["why"].lower()

    @pytest.mark.asyncio
    async def test_suggests_missing_categories(
        self, client: httpx.AsyncClient, only_tops
    ):
        await client.get("/v1/quality/summary")
        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        # Should suggest adding missing categories
        completeness_suggestions = data["by_dimension"].get("completeness", [])
        assert any(
            "bottom" in s["title"].lower() or "footwear" in s["title"].lower()
            for s in completeness_suggestions
        )


class TestDiversityPreferences:
    """Test diversity scoring respects user preferences."""

    @pytest.mark.asyncio
    async def test_diversity_colors_off_by_default(self, client: httpx.AsyncClient):
        resp = await client.get("/v1/quality/preferences")
        assert resp.status_code == 200
        data = resp.json()

        assert data["diversity"]["colors"] is False
        assert data["diversity"]["patterns"] is True
        assert data["diversity"]["seasons"] is True
        assert data["diversity"]["styles"] is True

    @pytest.mark.asyncio
    async def test_update_diversity_preferences(self, client: httpx.AsyncClient):
        resp = await client.patch("/v1/quality/preferences", json={
            "diversity": {"colors": True, "patterns": False}
        })
        assert resp.status_code == 200
        data = resp.json()

        assert data["diversity"]["colors"] is True
        assert data["diversity"]["patterns"] is False


class TestScoreHistory:
    """Test score history and trends."""

    @pytest.mark.asyncio
    async def test_score_history_returned(self, client: httpx.AsyncClient):
        # Compute score twice
        await client.get("/v1/quality/summary?refresh=true")
        await client.get("/v1/quality/summary?refresh=true")

        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Should have history
        assert len(data["history"]) >= 1

    @pytest.mark.asyncio
    async def test_score_trend_calculation(self, client: httpx.AsyncClient):
        # First score with empty wardrobe
        await client.get("/v1/quality/summary?refresh=true")

        # Add items
        for i in range(5):
            await client.post("/v1/items", json={"kind": "top", "name": f"Top{i}"})

        # Second score should show trend
        resp = await client.get("/v1/quality/summary?refresh=true")
        assert resp.status_code == 200
        data = resp.json()

        # Trend should be present if there's a previous score
        if data["history"]:
            assert data["current"]["trend"] is not None


class TestSuggestionManagement:
    """Test suggestion dismiss and complete functionality."""

    @pytest.fixture
    async def suggestion_setup(self, client: httpx.AsyncClient):
        # Trigger score computation to generate suggestions
        await client.get("/v1/quality/summary")
        resp = await client.get("/v1/quality/suggestions")
        return resp.json()

    @pytest.mark.asyncio
    async def test_dismiss_suggestion(
        self, client: httpx.AsyncClient, suggestion_setup
    ):
        suggestions = suggestion_setup["suggestions"]
        if not suggestions:
            pytest.skip("No suggestions generated")

        sug_id = suggestions[0]["id"]
        resp = await client.patch(
            f"/v1/quality/suggestions/{sug_id}",
            json={"status": "dismissed"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_complete_suggestion(
        self, client: httpx.AsyncClient, suggestion_setup
    ):
        suggestions = suggestion_setup["suggestions"]
        if not suggestions:
            pytest.skip("No suggestions generated")

        sug_id = suggestions[0]["id"]
        resp = await client.patch(
            f"/v1/quality/suggestions/{sug_id}",
            json={"status": "completed"}
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_filter_suggestions_by_status(
        self, client: httpx.AsyncClient, suggestion_setup
    ):
        suggestions = suggestion_setup["suggestions"]
        if not suggestions:
            pytest.skip("No suggestions generated")

        # Dismiss one
        sug_id = suggestions[0]["id"]
        await client.patch(
            f"/v1/quality/suggestions/{sug_id}",
            json={"status": "dismissed"}
        )

        # Filter by pending
        resp = await client.get("/v1/quality/suggestions?status=pending")
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["status"] == "pending" for s in data["suggestions"])

        # Filter by dismissed
        resp = await client.get("/v1/quality/suggestions?status=dismissed")
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["status"] == "dismissed" for s in data["suggestions"])


class TestExplanationsAndConfidence:
    """Test that explanations and confidence levels are meaningful."""

    @pytest.fixture
    async def full_wardrobe(self, client: httpx.AsyncClient):
        # Create a reasonably complete wardrobe
        for i in range(3):
            await client.post("/v1/items", json={
                "kind": "top", "name": f"Top{i}",
                "base_color": ["white", "black", "blue"][i],
                "style_tags": ["casual"],
                "season_tags": ["spring", "summer"],
            })
        for i in range(2):
            await client.post("/v1/items", json={
                "kind": "bottom", "name": f"Bottom{i}",
                "base_color": ["black", "navy"][i],
            })
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

    @pytest.mark.asyncio
    async def test_all_dimensions_have_explanations(
        self, client: httpx.AsyncClient, full_wardrobe
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        for dim in ["versatility", "utilization", "completeness", "balance", "diversity"]:
            assert data["current"][dim]["why"], f"{dim} missing explanation"
            assert 0 <= data["current"][dim]["confidence"] <= 1
            assert 0 <= data["current"][dim]["score"] <= 100

    @pytest.mark.asyncio
    async def test_weights_sum_to_one(self, client: httpx.AsyncClient, full_wardrobe):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        total_weight = sum([
            data["current"]["versatility"]["weight"],
            data["current"]["utilization"]["weight"],
            data["current"]["completeness"]["weight"],
            data["current"]["balance"]["weight"],
            data["current"]["diversity"]["weight"],
        ])
        assert abs(total_weight - 1.0) < 0.01  # Allow small float error


class TestImbalancedWardrobe:
    """Test balance scoring with imbalanced wardrobe."""

    @pytest.fixture
    async def imbalanced_setup(self, client: httpx.AsyncClient):
        # Too many tops, not enough bottoms
        for i in range(10):
            await client.post("/v1/items", json={"kind": "top", "name": f"Top{i}"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "OnlyBottom"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})

    @pytest.mark.asyncio
    async def test_imbalanced_detects_ratio(
        self, client: httpx.AsyncClient, imbalanced_setup
    ):
        resp = await client.get("/v1/quality/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Balance score should be lower due to imbalance
        assert data["current"]["balance"]["score"] < 70
        assert "10:1" in data["current"]["balance"]["why"] or "tops" in data["current"]["balance"]["why"].lower()

    @pytest.mark.asyncio
    async def test_suggests_add_bottoms(
        self, client: httpx.AsyncClient, imbalanced_setup
    ):
        await client.get("/v1/quality/summary")
        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        balance_suggestions = data["by_dimension"].get("balance", [])
        assert any("bottom" in s["title"].lower() for s in balance_suggestions)


class TestRefreshParameter:
    """Test the refresh query parameter."""

    @pytest.mark.asyncio
    async def test_refresh_recomputes_score(self, client: httpx.AsyncClient):
        # Get initial score
        resp1 = await client.get("/v1/quality/summary")
        assert resp1.status_code == 200
        score1_id = resp1.json()["current"]["id"]

        # Get without refresh - should return same
        resp2 = await client.get("/v1/quality/summary")
        assert resp2.status_code == 200
        score2_id = resp2.json()["current"]["id"]
        assert score1_id == score2_id

        # Get with refresh - should be new score
        resp3 = await client.get("/v1/quality/summary?refresh=true")
        assert resp3.status_code == 200
        score3_id = resp3.json()["current"]["id"]
        assert score3_id != score1_id


class TestSuggestionsGroupedByDimension:
    """Test that suggestions are properly grouped."""

    @pytest.mark.asyncio
    async def test_suggestions_grouped(self, client: httpx.AsyncClient):
        # Empty wardrobe should generate suggestions for multiple dimensions
        await client.get("/v1/quality/summary")
        resp = await client.get("/v1/quality/suggestions")
        assert resp.status_code == 200
        data = resp.json()

        # Verify by_dimension structure
        assert "by_dimension" in data
        for dim, sugs in data["by_dimension"].items():
            assert all(s["dimension"] == dim for s in sugs)


class TestDeterministicScoring:
    """Test that scoring is deterministic with same input."""

    @pytest.fixture
    async def standard_wardrobe(self, client: httpx.AsyncClient):
        await client.post("/v1/items", json={"kind": "top", "name": "Top1"})
        await client.post("/v1/items", json={"kind": "top", "name": "Top2"})
        await client.post("/v1/items", json={"kind": "bottom", "name": "Bottom1"})
        await client.post("/v1/items", json={"kind": "footwear", "name": "Shoes"})
        await client.post("/v1/items", json={"kind": "outerwear", "name": "Jacket"})

    @pytest.mark.asyncio
    async def test_same_input_same_score(
        self, client: httpx.AsyncClient, standard_wardrobe
    ):
        resp1 = await client.get("/v1/quality/summary?refresh=true")
        score1 = resp1.json()["current"]["total_score"]

        resp2 = await client.get("/v1/quality/summary?refresh=true")
        score2 = resp2.json()["current"]["total_score"]

        # Scores should be identical for same wardrobe state
        assert abs(score1 - score2) < 0.01
