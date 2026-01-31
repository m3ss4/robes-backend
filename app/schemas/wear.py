from pydantic import BaseModel
from typing import Optional, List


class PlannedOutfitWearOut(BaseModel):
    id: str
    outfit_id: str
    worn_date: str
    source: Optional[str] = None
    created_at: Optional[str] = None
    notes: Optional[str] = None
    event: Optional[str] = None
    mood: Optional[str] = None
    season: Optional[str] = None


class PlannedItemWearOut(BaseModel):
    id: str
    item_id: str
    worn_date: str
    source: Optional[str] = None
    created_at: Optional[str] = None
    notes: Optional[str] = None


class WearPlannedOut(BaseModel):
    outfits: List[PlannedOutfitWearOut]
    items: List[PlannedItemWearOut]
