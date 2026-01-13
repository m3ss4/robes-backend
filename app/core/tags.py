import re
import unicodedata
from typing import Iterable, Sequence

ALLOWED_SEASONS = {"spring", "summer", "autumn", "winter"}
ALLOWED_EVENTS = {
    "office",
    "business-formal",
    "business-casual",
    "smart-casual",
    "casual",
    "evening",
    "formal",
    "black-tie",
    "party",
    "wedding",
    "interview",
    "gym",
    "hiking",
    "beach",
    "travel",
    "outdoor",
}

def normalize_tag(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not (1 <= len(s) <= 24):
        raise ValueError("invalid_length")
    return s

def normalize_many(xs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs or []:
        t = normalize_tag(x)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out

def clamp_limits(
    style: Sequence[str], event: Sequence[str], season: Sequence[str]
) -> tuple[list[str], list[str], list[str]]:
    st = list(style)[:10]
    ev = list(event)[:6]
    se = [x for x in season if x in ALLOWED_SEASONS][:2]
    return st, ev, se
