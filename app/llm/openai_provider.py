import asyncio
import json
import os
from typing import Any, Optional

from pydantic import ValidationError

from app.llm.base import SuggestionProvider
from app.llm.types import LLMRequest, SuggestDraft, SuggestField
from app.llm.prompt_templates import build_system_prompt, build_user_prompt


class OpenAIProvider(SuggestionProvider):
    def __init__(self, client: Optional[Any] = None):
        self.client = client

    async def suggest(self, req: LLMRequest, *, timeout_ms: int) -> SuggestDraft:
        system = build_system_prompt()
        user = build_user_prompt(req.features, req.hints)

        async def _call():
            from openai import AsyncOpenAI

            client = self.client or AsyncOpenAI()
            resp = await client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "256")),
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content

        try:
            content = await asyncio.wait_for(_call(), timeout=timeout_ms / 1000.0)
            if not content:
                return SuggestDraft()
            data = json.loads(content)
            draft_dict = data.get("draft", {})
            parsed = {k: SuggestField(**v) for k, v in draft_dict.items() if isinstance(v, dict)}
            return SuggestDraft(**parsed)
        except (asyncio.TimeoutError, ValidationError, Exception):
            return SuggestDraft()
