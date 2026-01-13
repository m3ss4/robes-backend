from __future__ import annotations

from typing import Protocol

from app.services.llm.types import (
    ExplainOutfitInput,
    ExplainOutfitOutput,
    SuggestItemAttributesInput,
    SuggestItemAttributesOutput,
)


class LLMProvider(Protocol):
    async def suggest_item_attributes(
        self, payload: SuggestItemAttributesInput, *, timeout_ms: int
    ) -> SuggestItemAttributesOutput:
        ...

    async def explain_outfit(self, payload: ExplainOutfitInput, *, timeout_ms: int) -> ExplainOutfitOutput:
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
