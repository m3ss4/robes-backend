from pydantic import BaseModel
from typing import Optional, List


class OutfitMatchIn(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    image_content_type: Optional[str] = None
    min_confidence: Optional[float] = None
    max_per_slot: Optional[int] = None


class OutfitMatchItemOut(BaseModel):
    item_id: str
    slot: str
    confidence: float
    reason: Optional[str] = None


class OutfitMatchOut(BaseModel):
    matches: List[OutfitMatchItemOut]
    slots: List[str]
    missing_count: int = 0
    warnings: List[str]
    usage: Optional[dict] = None


class OutfitMatchQueueIn(BaseModel):
    image_url: str
    date: Optional[str] = None
    min_confidence: Optional[float] = None
    max_per_slot: Optional[int] = None


class OutfitMatchJobOut(BaseModel):
    job_id: str
    status: str
    image_url: str
    date: Optional[str] = None
    matches: Optional[List[OutfitMatchItemOut]] = None
    slots: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
    error: Optional[str] = None


class OutfitMatchJobListOut(BaseModel):
    jobs: List[OutfitMatchJobOut]
