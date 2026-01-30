from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Literal, Any, Dict, Generic, TypeVar

class ItemImageIn(BaseModel):
    url: str
    view: Optional[Literal["front","back","side"]] = "front"

class ItemImageOut(BaseModel):
    id: str
    url: str
    view: Literal["front","back","side"] = "front"
    bg_removed: bool = False
    bucket: Optional[str] = None
    key: Optional[str] = None
    kind: Optional[str] = None
    bytes: Optional[int] = None

class ItemCreate(BaseModel):
    kind: Literal["top","bottom","onepiece","outerwear","footwear","accessory","underlayer"]
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
    kind: Optional[Literal["top","bottom","onepiece","outerwear","footwear","accessory","underlayer"]] = None
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
    op: Literal["set","add","remove"]
    style_tags: Optional[List[str]] = None
    event_tags: Optional[List[str]] = None
    season_tags: Optional[List[str]] = None

class TagSuggestOut(BaseModel):
    suggestions: List[Dict[str, str]]

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


class OutfitItemIn(BaseModel):
    item_id: str
    slot: Literal["top","bottom","one_piece","outerwear","shoes","bag","accessory"]
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


class WearLogDeleteIn(BaseModel):
    deleted: Optional[bool] = None
    source: Optional[str] = None


class ItemWearLogIn(BaseModel):
    worn_at: Optional[str] = None
    source: Optional[str] = None


class ItemWearLogOut(BaseModel):
    id: str
    item_id: str
    worn_at: str
    worn_date: Optional[str] = None
    source: Optional[str] = None


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


class OutfitPhotoPresignIn(BaseModel):
    content_type: str


class OutfitPhotoPresignOut(BaseModel):
    key: str
    upload_url: str
    headers: Dict[str, str]
    cdn_url: str


class OutfitPhotoConfirmIn(BaseModel):
    key: str
    width: Optional[int] = None
    height: Optional[int] = None


class OutfitPhotoOut(BaseModel):
    id: str
    status: str
    created_at: str
    image_url: Optional[str] = None


class OutfitPhotoMatchedItem(BaseModel):
    item_id: str
    score: float
    slot: Optional[str] = None


class OutfitPhotoAnalysisOut(BaseModel):
    status: str
    matched_items: List[OutfitPhotoMatchedItem]
    matched_outfit_id: Optional[str] = None
    warnings: List[str]


class OutfitPhotoGetOut(BaseModel):
    outfit_photo: OutfitPhotoOut
    analysis: Optional[OutfitPhotoAnalysisOut] = None


class OutfitPhotoApplyIn(BaseModel):
    date: Optional[str] = None
    force_create: bool = False
    override_items: Optional[List[Dict[str, Any]]] = None


class OutfitPhotoApplyOut(BaseModel):
    outfit_id: str
    created: bool
    wore_logged: bool
    matched_items: List[OutfitPhotoMatchedItem]
    warnings: List[str]
    message: Optional[str] = None
