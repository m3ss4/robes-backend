from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict

from app.core.cache import cache_json_get, cache_json_set
from app.core.config import settings
from app.services.llm.providers.base import LLMProvider, NullProvider
from app.services.llm.providers.openai import OpenAIProvider
from app.services.llm.prompts import PROMPT_VERSION
from app.services.llm.types import (
    AskUserItemsInput,
    AskUserItemsOutput,
    ExplainOutfitInput,
    ExplainOutfitOutput,
    LLMUsage,
    SuggestItemAttributesInput,
    SuggestItemAttributesOutput,
    SuggestItemPairingsInput,
    SuggestItemPairingsOutput,
)

_provider: LLMProvider | None = None
logger = logging.getLogger("uvicorn.error")


def _hash_blob(data: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def _get_provider() -> LLMProvider:
    global _provider
    if _provider:
        return _provider
    if not settings.LLM_ENABLED:
        logger.info("llm:disabled")
        _provider = NullProvider()
        return _provider
    name = (settings.LLM_PROVIDER or "local").lower()
    if name == "openai":
        logger.info("llm:provider=openai model_attributes=%s model_explain=%s", settings.LLM_MODEL_ATTRIBUTES, settings.LLM_MODEL_EXPLAIN)
        _provider = OpenAIProvider(settings.LLM_MODEL_ATTRIBUTES, settings.LLM_MODEL_EXPLAIN)
    else:
        logger.info("llm:provider=disabled name=%s", name)
        _provider = NullProvider()
    return _provider


async def suggest_item_attributes(payload: SuggestItemAttributesInput) -> SuggestItemAttributesOutput:
    payload.prompt_version = payload.prompt_version or PROMPT_VERSION
    if not settings.LLM_ENABLED:
        return SuggestItemAttributesOutput(
            suggestions={},
            usage=LLMUsage(model="disabled", cached=True, prompt_version=payload.prompt_version),
        )

    cache_key = f"llm:attrs:{payload.prompt_version}:{_hash_blob({'f': payload.features, 't': payload.taxonomy})}"
    cached = await cache_json_get(cache_key)
    if cached:
        out = SuggestItemAttributesOutput.model_validate(cached)
        out.usage.cached = True
        out.usage.cache_key = cache_key
        return out

    provider = _get_provider()
    out = await provider.suggest_item_attributes(payload, timeout_ms=settings.LLM_SUGGEST_TIMEOUT_MS)
    out.usage.cached = False
    out.usage.cache_key = cache_key
    await cache_json_set(cache_key, out.model_dump(), settings.LLM_CACHE_TTL_S)
    return out


async def explain_outfit(payload: ExplainOutfitInput) -> ExplainOutfitOutput:
    payload.prompt_version = payload.prompt_version or PROMPT_VERSION
    if not settings.LLM_ENABLED:
        return ExplainOutfitOutput(
            explanations=[],
            tiebreak=None,
            usage=LLMUsage(model="disabled", cached=True, prompt_version=payload.prompt_version),
        )

    cache_key = f"llm:explain:{payload.prompt_version}:{_hash_blob({'m': payload.metrics, 'c': payload.context, 'i': payload.items})}"
    cached = await cache_json_get(cache_key)
    if cached:
        out = ExplainOutfitOutput.model_validate(cached)
        out.usage.cached = True
        out.usage.cache_key = cache_key
        return out

    provider = _get_provider()
    out = await provider.explain_outfit(payload, timeout_ms=settings.LLM_SUGGEST_TIMEOUT_MS)
    out.usage.cached = False
    out.usage.cache_key = cache_key
    await cache_json_set(cache_key, out.model_dump(), settings.LLM_CACHE_TTL_S)
    return out


async def suggest_item_pairings(payload: SuggestItemPairingsInput) -> SuggestItemPairingsOutput:
    payload.prompt_version = payload.prompt_version or PROMPT_VERSION
    if not settings.LLM_ENABLED:
        return SuggestItemPairingsOutput(
            suggestions=[],
            usage=LLMUsage(model="disabled", cached=True, prompt_version=payload.prompt_version),
        )

    provider = _get_provider()
    out = await provider.suggest_item_pairings(payload, timeout_ms=settings.LLM_SUGGEST_TIMEOUT_MS)
    out.usage.cached = False
    return out


async def ask_user_items(payload: AskUserItemsInput) -> AskUserItemsOutput:
    payload.prompt_version = payload.prompt_version or PROMPT_VERSION
    if not settings.LLM_ENABLED:
        return AskUserItemsOutput(
            answer="",
            usage=LLMUsage(model="disabled", cached=True, prompt_version=payload.prompt_version),
        )

    provider = _get_provider()
    out = await provider.ask_user_items(payload, timeout_ms=settings.LLM_SUGGEST_TIMEOUT_MS)
    out.usage.cached = False
    return out
