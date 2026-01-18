from __future__ import annotations

from typing import Protocol

from app.services.llm.types import (
    AskUserItemsInput,
    AskUserItemsOutput,
    ExplainOutfitInput,
    ExplainOutfitOutput,
    SuggestItemAttributesInput,
    SuggestItemAttributesOutput,
    SuggestItemPairingsInput,
    SuggestItemPairingsOutput,
)


class LLMProvider(Protocol):
    async def suggest_item_attributes(
        self, payload: SuggestItemAttributesInput, *, timeout_ms: int
    ) -> SuggestItemAttributesOutput:
        ...

    async def explain_outfit(self, payload: ExplainOutfitInput, *, timeout_ms: int) -> ExplainOutfitOutput:
        ...

    async def suggest_item_pairings(
        self, payload: SuggestItemPairingsInput, *, timeout_ms: int
    ) -> SuggestItemPairingsOutput:
        ...

    async def ask_user_items(self, payload: AskUserItemsInput, *, timeout_ms: int) -> AskUserItemsOutput:
        ...


class NullProvider:
    """Safety net provider used when LLM is disabled."""

    name = "disabled"

    async def suggest_item_attributes(
        self, payload: SuggestItemAttributesInput, *, timeout_ms: int
    ) -> SuggestItemAttributesOutput:
        from app.services.llm.types import SuggestItemAttributesOutput, LLMUsage

        return SuggestItemAttributesOutput(
            suggestions={},
            usage=LLMUsage(model=self.name, prompt_version=payload.prompt_version, cached=True),
        )

    async def explain_outfit(self, payload: ExplainOutfitInput, *, timeout_ms: int) -> ExplainOutfitOutput:
        from app.services.llm.types import ExplainOutfitOutput, LLMUsage

        return ExplainOutfitOutput(
            explanations=[],
            tiebreak=None,
            usage=LLMUsage(model=self.name, prompt_version=payload.prompt_version, cached=True),
        )

    async def suggest_item_pairings(
        self, payload: SuggestItemPairingsInput, *, timeout_ms: int
    ) -> SuggestItemPairingsOutput:
        from app.services.llm.types import SuggestItemPairingsOutput, LLMUsage

        return SuggestItemPairingsOutput(
            suggestions=[],
            usage=LLMUsage(model=self.name, prompt_version=payload.prompt_version, cached=True),
        )

    async def ask_user_items(self, payload: AskUserItemsInput, *, timeout_ms: int) -> AskUserItemsOutput:
        from app.services.llm.types import AskUserItemsOutput, LLMUsage

        return AskUserItemsOutput(
            answer="",
            usage=LLMUsage(model=self.name, prompt_version=payload.prompt_version, cached=True),
        )
