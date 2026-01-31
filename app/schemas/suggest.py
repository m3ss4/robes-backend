from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Any, Dict, Generic, TypeVar


T = TypeVar("T")


class SuggestField(BaseModel, Generic[T]):
    value: Optional[T] = None
    confidence: float
    source: str
    reason: Optional[str] = None


class SuggestDraft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    category: Optional[SuggestField[str]] = None
    type: Optional[SuggestField[str]] = Field(None, alias="type")
    base_color: Optional[SuggestField[str]] = None
    tone: Optional[SuggestField[str]] = None
    warmth: Optional[SuggestField[int]] = None
    formality: Optional[SuggestField[float]] = None
    layer_role: Optional[SuggestField[str]] = None
    pattern: Optional[SuggestField[str]] = None
    fabric_kind: Optional[SuggestField[str]] = None
    material: Optional[SuggestField[str]] = None
    season_tags: Optional[SuggestField[List[str]]] = None
    event_tags: Optional[SuggestField[List[str]]] = None
    style_tags: Optional[SuggestField[List[str]]] = None


class SuggestAttributesIn(BaseModel):
    image_url: Optional[str] = None
    image_b64: Optional[str] = None
    image_urls: Optional[List[str]] = None
    image_b64s: Optional[List[str]] = None
    item_id: Optional[str] = None
    image_ids: Optional[List[str]] = None
    hints: Optional[Dict[str, Any]] = None
    lock_fields: Optional[List[str]] = None
    use_vision: Optional[bool] = None
    force: Optional[bool] = None


class SuggestAttributesOut(BaseModel):
    draft: SuggestDraft
    pending_features: Optional[bool] = None
