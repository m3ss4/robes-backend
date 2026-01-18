from __future__ import annotations

import json
from typing import Dict, List

from app.services.llm.types import ExplainOutfitInput, SuggestItemAttributesInput, SuggestItemPairingsInput, AskUserItemsInput


PROMPT_VERSION = "p1"

ATTR_SYS = (
    "You label clothing attributes using the provided taxonomy. "
    "Respond ONLY with JSON matching {\"suggestions\": {field: {\"value\": ..., \"confidence\": 0-1, \"source\": \"llm\", \"rationale\": \"...\"}}}."
)

EXPLAIN_SYS = (
    "You explain outfit scores using only the provided numeric metrics and item descriptors. "
    "Return JSON: {\"explanations\": [\"...\"], \"tiebreak\": \"A|B|none\"}. Keep it concise."
)

PAIR_SYS = (
    "You are ranking how well clothing items pair together. "
    "Return ONLY JSON: {\"suggestions\": [{\"item_id\": \"...\", \"score\": 0-100}]} "
    "sorted best-to-worst. Use the provided attributes and attribute_sources; if source==\"user\" treat as 100% confident."
)

ASK_SYS = (
    "You answer user questions using only the provided item metadata. "
    "Return ONLY JSON: {\"answer\": \"...\"}. If the answer is unknown, say you don't know."
)


def build_attributes_prompt(payload: SuggestItemAttributesInput) -> List[Dict[str, str]]:
    user_payload = {
        "taxonomy": payload.taxonomy,
        "features": payload.features,
        "current": payload.current,
        "locked": payload.locked,
        "allow_vision": payload.allow_vision,
        "image_url": payload.image_url,
        "prompt_version": payload.prompt_version or PROMPT_VERSION,
    }
    return [
        {"role": "system", "content": ATTR_SYS},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_explain_prompt(payload: ExplainOutfitInput) -> List[Dict[str, str]]:
    user_payload = {
        "metrics": payload.metrics,
        "context": payload.context,
        "items": payload.items,
        "prompt_version": payload.prompt_version or PROMPT_VERSION,
        "compare": payload.compare,
    }
    return [
        {"role": "system", "content": EXPLAIN_SYS},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_pairing_prompt(payload: SuggestItemPairingsInput) -> List[Dict[str, str]]:
    user_payload = {
        "base_item": payload.base_item,
        "candidates": [c.model_dump() for c in payload.candidates],
        "limit": payload.limit,
        "prompt_version": payload.prompt_version or PROMPT_VERSION,
    }
    return [
        {"role": "system", "content": PAIR_SYS},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]


def build_ask_items_prompt(payload: AskUserItemsInput) -> List[Dict[str, str]]:
    user_payload = {
        "question": payload.question,
        "items": payload.items,
        "prompt_version": payload.prompt_version or PROMPT_VERSION,
    }
    return [
        {"role": "system", "content": ASK_SYS},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
