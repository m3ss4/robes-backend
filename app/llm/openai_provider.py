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

    async def suggest_with_vision(self, req: LLMRequest, image_url: str, *, timeout_ms: int) -> SuggestDraft:
        system = build_system_prompt()
        user_text = build_user_prompt(req.features, req.hints)

        async def _call():
            from openai import AsyncOpenAI

            client = self.client or AsyncOpenAI()
            resp = await client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system},
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user_text},
                            {"type": "input_image", "image_url": image_url},
                        ],
                    },
                ],
                temperature=0.2,
                max_tokens=int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "256")),
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content

        return await self._parse_suggest_response(_call, timeout_ms)

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

        if req.ambiguity.clip_family_ambiguous or req.ambiguity.clip_pattern_ambiguous:
            if req.image_url:
                draft = await self.suggest_with_vision(req, req.image_url, timeout_ms=timeout_ms)
                return self._apply_field_authority(req, draft)
        draft = await self._parse_suggest_response(_call, timeout_ms)
        return self._apply_field_authority(req, draft)

    async def _parse_suggest_response(self, call, timeout_ms: int) -> SuggestDraft:
        try:
            content = await asyncio.wait_for(call(), timeout=timeout_ms / 1000.0)
            if not content:
                return SuggestDraft()
            data = json.loads(content)
            draft_dict = data.get("draft", {})
            parsed = {k: SuggestField(**v) for k, v in draft_dict.items() if isinstance(v, dict)}
            return SuggestDraft(**parsed)
        except (asyncio.TimeoutError, ValidationError, Exception):
            return SuggestDraft()

    def _apply_field_authority(self, req: LLMRequest, draft: SuggestDraft) -> SuggestDraft:
        features = req.features or {}
        clip_pattern = features.get("clip_pattern") or features.get("pattern")

        def clear_field(field: SuggestField, reason: str) -> None:
            field.value = None
            field.confidence = 0.0
            field.source = "rule"
            field.reason = reason

        if not req.ambiguity.clip_family_ambiguous:
            clear_field(draft.category, "blocked_by_authority")
        if not req.ambiguity.clip_family_ambiguous or (draft.type.confidence or 0.0) < 0.6:
            clear_field(draft.type, "blocked_by_authority")

        clear_field(draft.base_color, "blocked_by_authority")

        allow_pattern_override = False
        if req.ambiguity.clip_pattern_ambiguous:
            allow_pattern_override = True
        elif clip_pattern == "stripe" and draft.pattern.value and draft.pattern.value != "stripe":
            allow_pattern_override = True
        if not allow_pattern_override:
            clear_field(draft.pattern, "blocked_by_authority")

        if draft.material.value is not None:
            draft.material.confidence = min(draft.material.confidence or 0.0, 0.6)
            draft.material.source = "llm"

        return draft
