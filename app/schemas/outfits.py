from pydantic import BaseModel
from typing import Optional, List, Literal, Any, Dict


class OutfitItemIn(BaseModel):
    item_id: str
    slot: Literal["top", "bottom", "one_piece", "outerwear", "shoes", "bag", "accessory"]
    position: Optional[int] = 0


class OutfitCreate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    source: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    items: List[OutfitItemIn]


class OutfitOut(BaseModel):
    id: str
    name: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    feedback: Optional[Dict[str, Any]] = None
    attributes: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    primary_image_url: Optional[str] = None
    items: List[OutfitItemIn]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    items_detail: Optional[List[Dict[str, Any]]] = None


class WearLogIn(BaseModel):
    worn_at: Optional[str] = None
    worn_date: Optional[str] = None
    event: Optional[str] = None
    location: Optional[str] = None
    weather: Optional[Dict[str, Any]] = None
    season: Optional[str] = None
    mood: Optional[str] = None
    notes: Optional[str] = None
    source: Optional[str] = None


class WearLogOut(BaseModel):
    id: str
    outfit_id: str
    worn_at: str
    worn_date: Optional[str] = None
    source: Optional[str] = None
    event: Optional[str] = None
    location: Optional[str] = None
    season: Optional[str] = None
    mood: Optional[str] = None
    notes: Optional[str] = None
    is_future: Optional[bool] = None


class WearLogDeleteIn(BaseModel):
    deleted: Optional[bool] = None
    source: Optional[str] = None


class ScoreRequest(BaseModel):
    items: List[OutfitItemIn]
    context: Optional[Dict[str, Any]] = None


class ScoreOut(BaseModel):
    metrics: Dict[str, Any]


class OutfitFeedbackIn(BaseModel):
    score_grade: Optional[Literal["A", "B", "C", "D", "E", "F"]] = None
    feel_tags: Optional[List[str]] = None
    notes: Optional[str] = None


class OutfitFeedbackOut(BaseModel):
    outfit_id: str
    feedback: OutfitFeedbackIn
    updated_at: Optional[str] = None


class OutfitDecisionIn(BaseModel):
    decision: Literal["accept", "reject"]


class OutfitSuggestIn(BaseModel):
    mood: Optional[str] = "calm"
    event: Optional[str] = "office"
    timeOfDay: Optional[str] = "morning"
    datetime: Optional[str] = None
    location: Optional[Any] = None


class Outfit(BaseModel):
    id: str
    score: float
    rationale: list[str]
    slots: dict[str, str]


class OutfitSuggestOut(BaseModel):
    session_id: Optional[str] = None
    outfits: list[Outfit]
