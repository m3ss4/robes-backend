from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List

from openai import AsyncOpenAI

import logging

from app.services.llm.types import (
    AskUserItemsInput,
    AskUserItemsOutput,
    ExplainOutfitInput,
    ExplainOutfitOutput,
    LLMUsage,
    PairingSuggestionOut,
    SuggestFieldOut,
    SuggestItemAttributesInput,
    SuggestItemAttributesOutput,
    SuggestItemPairingsInput,
    SuggestItemPairingsOutput,
)
from app.services.llm.prompts import build_attributes_prompt, build_explain_prompt, build_pairing_prompt, build_ask_items_prompt

logger = logging.getLogger("uvicorn.error")


class OpenAIProvider:
    def __init__(self, model_attributes: str, model_explain: str):
        self.client = AsyncOpenAI()
        self.model_attributes = model_attributes
        self.model_explain = model_explain

    async def _chat(self, messages: List[Dict[str, str]], model: str, timeout_ms: int) -> Dict[str, Any]:
        start = time.perf_counter()
        logger.info("llm:openai request model=%s timeout_ms=%s", model, timeout_ms)
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(model=model, messages=messages, temperature=0.2),
                timeout=timeout_ms / 1000.0,
            )
        except asyncio.TimeoutError:
            logger.warning("llm:openai timeout model=%s timeout_ms=%s", model, timeout_ms)
            raise
        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0].message.content if resp.choices else "{}"
        return {
            "content": choice,
            "latency_ms": latency_ms,
            "tokens_in": getattr(resp.usage, "prompt_tokens", 0) if resp.usage else 0,
            "tokens_out": getattr(resp.usage, "completion_tokens", 0) if resp.usage else 0,
        }

    async def suggest_item_attributes(
        self, payload: SuggestItemAttributesInput, *, timeout_ms: int
    ) -> SuggestItemAttributesOutput:
        messages = build_attributes_prompt(payload)
        res = await self._chat(messages, self.model_attributes, timeout_ms)
        suggestions = _safe_parse_suggestions(res["content"])
        return SuggestItemAttributesOutput(
            suggestions=suggestions,
            usage=LLMUsage(
                model=self.model_attributes,
                tokens_in=res["tokens_in"],
                tokens_out=res["tokens_out"],
                latency_ms=res["latency_ms"],
                prompt_version=payload.prompt_version,
            ),
        )

    async def explain_outfit(self, payload: ExplainOutfitInput, *, timeout_ms: int) -> ExplainOutfitOutput:
        messages = build_explain_prompt(payload)
        res = await self._chat(messages, self.model_explain, timeout_ms)
        explanations, tiebreak = _safe_parse_explanations(res["content"])
        return ExplainOutfitOutput(
            explanations=explanations,
            tiebreak=tiebreak,
            usage=LLMUsage(
                model=self.model_explain,
                tokens_in=res["tokens_in"],
                tokens_out=res["tokens_out"],
                latency_ms=res["latency_ms"],
                prompt_version=payload.prompt_version,
            ),
        )

    async def suggest_item_pairings(
        self, payload: SuggestItemPairingsInput, *, timeout_ms: int
    ) -> SuggestItemPairingsOutput:
        messages = build_pairing_prompt(payload)
        res = await self._chat(messages, self.model_attributes, timeout_ms)
        suggestions = _safe_parse_pairings(res["content"])
        return SuggestItemPairingsOutput(
            suggestions=suggestions,
            usage=LLMUsage(
                model=self.model_attributes,
                tokens_in=res["tokens_in"],
                tokens_out=res["tokens_out"],
                latency_ms=res["latency_ms"],
                prompt_version=payload.prompt_version,
            ),
        )

    async def ask_user_items(self, payload: AskUserItemsInput, *, timeout_ms: int) -> AskUserItemsOutput:
        messages = build_ask_items_prompt(payload)
        res = await self._chat(messages, self.model_explain, timeout_ms)
        answer = _safe_parse_answer(res["content"])
        return AskUserItemsOutput(
            answer=answer,
            usage=LLMUsage(
                model=self.model_explain,
                tokens_in=res["tokens_in"],
                tokens_out=res["tokens_out"],
                latency_ms=res["latency_ms"],
                prompt_version=payload.prompt_version,
            ),
        )


def _safe_parse_suggestions(raw: str) -> Dict[str, SuggestFieldOut]:
    try:
        data = json.loads(raw)
        return {k: SuggestFieldOut.model_validate(v) for k, v in data.get("suggestions", data).items()}
    except Exception:
        return {}


def _safe_parse_explanations(raw: str) -> tuple[List[str], str | None]:
    try:
        data = json.loads(raw)
        return data.get("explanations", []), data.get("tiebreak")
    except Exception:
        # Allow plain-text bullet responses
        lines = [ln.strip("- ").strip() for ln in raw.splitlines() if ln.strip()]
        return lines, None


def _safe_parse_pairings(raw: str) -> List[PairingSuggestionOut]:
    try:
        data = json.loads(raw)
        suggestions = data.get("suggestions", data)
        return [PairingSuggestionOut.model_validate(s) for s in suggestions if isinstance(s, dict)]
    except Exception:
        return []


def _safe_parse_answer(raw: str) -> str:
    try:
        data = json.loads(raw)
        return str(data.get("answer", "")).strip()
    except Exception:
        return raw.strip()
