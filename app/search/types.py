from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class SearchQuery:
    text: str
    limit: int = 20


@dataclass(frozen=True)
class SearchHit:
    id: str
    score: float
    title: Optional[str] = None
    image_url: Optional[str] = None


@dataclass(frozen=True)
class SearchResult:
    hits: List[SearchHit]
    took_ms: int
