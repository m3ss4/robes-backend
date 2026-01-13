import asyncio

import pytest

from app.llm.base import ProviderRegistry
from app.llm.types import LLMRequest, SuggestDraft, SuggestField
from app.services.suggest import suggest_with_provider


class DummyProvider:
    def __init__(self):
        self.calls = 0

    async def suggest(self, req: LLMRequest, *, timeout_ms: int) -> SuggestDraft:
        self.calls += 1
        return SuggestDraft(
            material=SuggestField(value="cotton", confidence=0.7, source="llm", reason="stub"),
        )


@pytest.mark.asyncio
async def test_provider_and_cache(monkeypatch):
    prov = DummyProvider()
    ProviderRegistry.register("local", prov)
    monkeypatch.setenv("LLM_PROVIDER", "local")
    draft1, meta1 = await suggest_with_provider({"base_color": "navy"}, {}, [])
    draft2, meta2 = await suggest_with_provider({"base_color": "navy"}, {}, [])
    assert draft1.material.value == "cotton"
    assert draft2.material.value == "cotton"
    assert prov.calls == 1  # cache hit second time
    assert meta2["cached"] is True


@pytest.mark.asyncio
async def test_timeout_fallback(monkeypatch):
    class SlowProvider:
        async def suggest(self, req: LLMRequest, *, timeout_ms: int) -> SuggestDraft:
            await asyncio.sleep(2)
            return SuggestDraft()

    ProviderRegistry.register("local", SlowProvider())
    monkeypatch.setenv("LLM_PROVIDER", "local")
    draft, meta = await suggest_with_provider({}, {}, [])
    assert draft.material.value is None
