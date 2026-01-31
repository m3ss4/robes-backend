from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Any, Dict


class ItemImageIn(BaseModel):
    url: str
    view: Optional[Literal["front", "back", "side"]] = "front"


class ItemImageOut(BaseModel):
    id: str
    url: str
    view: Literal["front", "back", "side"] = "front"
    bg_removed: bool = False
    bucket: Optional[str] = None
    key: Optional[str] = None
    kind: Optional[str] = None
    bytes: Optional[int] = None


class ItemCreate(BaseModel):
    kind: Literal["top", "bottom", "onepiece", "outerwear", "footwear", "accessory", "underlayer"]
    attribute_sources: Optional[Dict[str, Literal["user", "suggested"]]] = None
    category: Optional[str] = None
    type: Optional[str] = Field(None, alias="type")
    fit: Optional[str] = None
    fabric_kind: Optional[str] = None
    pattern: Optional[str] = None
    tone: Optional[str] = None
    layer_role: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    base_color: Optional[str] = None
    material: Optional[str] = None
    warmth: Optional[int] = None
    formality: Optional[float] = None
    style_tags: Optional[List[str]] = None
    event_tags: Optional[List[str]] = None
    season_tags: Optional[List[str]] = None
    images: Optional[List[ItemImageIn]] = None


class ItemUpdate(BaseModel):
    kind: Optional[Literal["top", "bottom", "onepiece", "outerwear", "footwear", "accessory", "underlayer"]] = None
    status: Optional[str] = None
    attribute_sources: Optional[Dict[str, Literal["user", "suggested"]]] = None
    category: Optional[str] = None
    type: Optional[str] = Field(None, alias="type")
    fit: Optional[str] = None
    fabric_kind: Optional[str] = None
    pattern: Optional[str] = None
    tone: Optional[str] = None
    layer_role: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    base_color: Optional[str] = None
    material: Optional[str] = None
    warmth: Optional[int] = None
    formality: Optional[float] = None


class ItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    kind: str
    status: Optional[str] = "active"
    attribute_sources: Optional[Dict[str, Dict[str, Any]]] = None
    pairing_suggestions: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    type: Optional[str] = Field(None, alias="type")
    fit: Optional[str] = None
    fabric_kind: Optional[str] = None
    pattern: Optional[str] = None
    tone: Optional[str] = None
    layer_role: Optional[str] = None
    name: Optional[str] = None
    brand: Optional[str] = None
    base_color: Optional[str] = None
    warmth: Optional[int] = None
    formality: Optional[float] = None
    style_tags: Optional[List[str]] = None
    event_tags: Optional[List[str]] = None
    season_tags: Optional[List[str]] = None
    images: Optional[List[ItemImageOut]] = None


class TagPatch(BaseModel):
    op: Literal["set", "add", "remove"]
    style_tags: Optional[List[str]] = None
    event_tags: Optional[List[str]] = None
    season_tags: Optional[List[str]] = None


class TagSuggestOut(BaseModel):
    suggestions: List[Dict[str, str]]


class ItemWearLogIn(BaseModel):
    worn_at: Optional[str] = None
    worn_date: Optional[str] = None
    source: Optional[str] = None


class ItemWearLogOut(BaseModel):
    id: str
    item_id: str
    worn_at: str
    worn_date: Optional[str] = None
    source: Optional[str] = None
    is_future: Optional[bool] = None


class ItemWearLogDeleteIn(BaseModel):
    deleted: Optional[bool] = None
    source: Optional[str] = None


class ItemPairingRequest(BaseModel):
    limit: Optional[int] = 10


class ItemPairingSuggestion(BaseModel):
    item_id: str
    score: float


class ItemPairingResponse(BaseModel):
    item_id: str
    category: str
    cached: bool = False
    suggestions: List[ItemPairingSuggestion]


class AskUserItemsIn(BaseModel):
    question: str


class AskUserItemsOut(BaseModel):
    answer: str
    usage: Dict[str, Any]
