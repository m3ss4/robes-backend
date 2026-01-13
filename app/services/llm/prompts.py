from __future__ import annotations

import json
from typing import Dict, List

from app.services.llm.types import ExplainOutfitInput, SuggestItemAttributesInput


PROMPT_VERSION = "p1"

ATTR_SYS = (
    "You label clothing attributes using the provided taxonomy. "
    "Respond ONLY with JSON matching {\"suggestions\": {field: {\"value\": ..., \"confidence\": 0-1, \"source\": \"llm\", \"rationale\": \"...\"}}}."
)

EXPLAIN_SYS = (
    "You explain outfit scores using only the provided numeric metrics and item descriptors. "
    "Return JSON: {\"explanations\": [\"...\"], \"tiebreak\": \"A|B|none\"}. Keep it concise."
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
