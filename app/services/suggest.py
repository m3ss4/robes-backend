import asyncio
import hashlib
import json
import os
import time
from typing import Dict, List

from app.llm.base import ProviderRegistry
from app.llm.types import LLMRequest, SuggestDraft
from app.core.cache import cache_json_get, cache_json_set

CACHE_TTL = int(os.getenv("LLM_CACHE_TTL_SECONDS", "86400"))
TIMEOUT_MS = int(os.getenv("LLM_TIMEOUT_MS", "1200"))
PROVIDER_NAME = os.getenv("LLM_PROVIDER", "local")


def _hash_features(features: Dict, hints: Dict) -> str:
    blob = json.dumps({"f": features, "h": hints}, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


async def suggest_with_provider(features: Dict, hints: Dict, lock_fields: List[str]) -> tuple[SuggestDraft, Dict]:
    cache_key = f"suggest:{_hash_features(features, hints)}"
    cached = await cache_json_get(cache_key)
    if cached:
        return SuggestDraft.model_validate(cached), {"cached": True, "provider": PROVIDER_NAME, "latency_ms": 0, "tokens": 0}

    provider = ProviderRegistry.get(PROVIDER_NAME)
    req = LLMRequest(features=features, hints=hints, lock_fields=lock_fields)
    start = time.perf_counter()
    try:
        draft = await asyncio.wait_for(provider.suggest(req, timeout_ms=TIMEOUT_MS), timeout=TIMEOUT_MS / 1000.0 + 0.1)
    except asyncio.TimeoutError:
        draft = SuggestDraft()
    latency_ms = int((time.perf_counter() - start) * 1000)

    draft.lock(lock_fields)
    await cache_json_set(cache_key, draft.model_dump(), CACHE_TTL)
    meta = {"cached": False, "provider": PROVIDER_NAME, "latency_ms": latency_ms, "tokens": getattr(provider, "last_tokens", 0)}
    return draft, meta
