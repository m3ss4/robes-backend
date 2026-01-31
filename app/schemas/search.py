from typing import List, Optional
from pydantic import BaseModel


class SearchHitOut(BaseModel):
    id: str
    score: float
    title: Optional[str] = None
    image_url: Optional[str] = None


class SearchItemsOut(BaseModel):
    took_ms: int
    hits: List[SearchHitOut]


class SearchOutfitsOut(BaseModel):
    took_ms: int
    hits: List[SearchHitOut]
