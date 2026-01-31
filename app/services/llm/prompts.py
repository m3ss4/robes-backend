from __future__ import annotations

import json
from typing import Dict, List, Any

from app.services.llm.types import (
    ExplainOutfitInput,
    SuggestItemAttributesInput,
    SuggestItemPairingsInput,
    AskUserItemsInput,
    OutfitSlotDetectInput,
    OutfitItemMatchInput,
)


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

OUTFIT_SLOT_SYS = (
    "You are analyzing an outfit photo. Identify which clothing slots are visible: "
    "onepiece, top, bottom, outerwear, footwear, accessory. "
    "Return ONLY JSON: {\"slots\": [\"...\"], \"missing_count\": 0}. "
    "If a onepiece is visible, do NOT include top or bottom. "
    "If unsure, include the plausible slots and set missing_count to 0."
)

OUTFIT_MATCH_SYS = (
    "You match the outfit photo to candidate inventory items for a single slot. "
    "Return ONLY JSON: {\"matches\": [{\"item_id\": \"...\", \"confidence\": 0-1, \"reason\": \"...\"}], "
    "\"missing_count\": 0}. "
    "Only include matches if confidence is high; otherwise return an empty matches list. "
    "Use the outfit photo and candidate images/metadata."
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


def build_outfit_slot_prompt(payload: OutfitSlotDetectInput) -> List[Dict[str, Any]]:
    content = [
        {
            "type": "input_text",
            "text": json.dumps(
                {
                    "task": "detect_slots",
                    "prompt_version": payload.prompt_version or PROMPT_VERSION,
                },
                ensure_ascii=False,
            ),
        },
        {"type": "input_image", "image_url": payload.image_url},
    ]
    return [
        {"role": "system", "content": OUTFIT_SLOT_SYS},
        {"role": "user", "content": content},
    ]


def build_outfit_match_prompt(payload: OutfitItemMatchInput) -> List[Dict[str, Any]]:
    content: List[Dict[str, Any]] = [
        {
            "type": "input_text",
            "text": json.dumps(
                {
                    "task": "match_items",
                    "slot": payload.slot,
                    "min_confidence": payload.min_confidence,
                    "prompt_version": payload.prompt_version or PROMPT_VERSION,
                },
                ensure_ascii=False,
            ),
        },
        {"type": "input_image", "image_url": payload.image_url},
    ]
    for idx, cand in enumerate(payload.candidates, start=1):
        content.append(
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "candidate_index": idx,
                        "item_id": cand.item_id,
                        "category": cand.category,
                        "type": cand.type,
                        "base_color": cand.base_color,
                        "pattern": cand.pattern,
                        "fabric_kind": cand.fabric_kind,
                        "brand": cand.brand,
                        "name": cand.name,
                        "similarity": cand.similarity,
                    },
                    ensure_ascii=False,
                ),
            }
        )
        content.append({"type": "input_image", "image_url": cand.image_url})
    return [
        {"role": "system", "content": OUTFIT_MATCH_SYS},
        {"role": "user", "content": content},
    ]
