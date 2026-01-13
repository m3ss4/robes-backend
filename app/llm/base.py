from __future__ import annotations
from typing import Protocol
from app.llm.types import LLMRequest, SuggestDraft


class SuggestionProvider(Protocol):
    async def suggest(self, req: LLMRequest, *, timeout_ms: int) -> SuggestDraft:
        ...


class ProviderRegistry:
    _providers: dict[str, SuggestionProvider] = {}

    @classmethod
    def register(cls, name: str, provider: SuggestionProvider) -> None:
        cls._providers[name] = provider

    @classmethod
    def get(cls, name: str) -> SuggestionProvider:
        if name not in cls._providers:
            raise ValueError(f"Unknown provider: {name}")
        return cls._providers[name]
