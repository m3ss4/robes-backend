import json
from app.core.tags import ALLOWED_EVENTS, ALLOWED_SEASONS


def build_system_prompt() -> str:
    return (
        "You are a wardrobe taxonomy normalizer. Use ONLY the allowed values provided. "
        "If unsure, choose the most generic likely option. "
        "Output JSON with a top-level 'draft' object where each key is a field "
        'containing {"value":..., "confidence": float, "source": "llm", "reason": string}. '
        "Never output keys that are not listed. "
        "Do not describe images; use the provided feature summary."
    )


def build_user_prompt(features: dict, hints: dict) -> str:
    payload = {
        "features": features,
        "hints": hints,
        "allowed": {
            "season_tags": sorted(ALLOWED_SEASONS),
            "event_tags": sorted(ALLOWED_EVENTS),
        },
        "needs": ["material", "season_tags", "event_tags", "style_tags", "tone", "formality", "warmth"],
    }
    return json.dumps(payload, ensure_ascii=False)
