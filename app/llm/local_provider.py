from app.llm.base import SuggestionProvider
from app.llm.types import LLMRequest, SuggestDraft


class LocalProvider(SuggestionProvider):
    async def suggest(self, req: LLMRequest, *, timeout_ms: int) -> SuggestDraft:
        return SuggestDraft()
