from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


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
    matched_items: List[OutfitPhotoMatchedItem] = Field(default_factory=list)
    matched_outfit_id: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class OutfitPhotoGetOut(BaseModel):
    outfit_photo: OutfitPhotoOut
    analysis: Optional[OutfitPhotoAnalysisOut] = None


class OutfitPhotoHealthOut(BaseModel):
    ok: bool
    pgvector_installed: bool
    embedding_column_type: Optional[str] = None
    embedding_column_udt: Optional[str] = None
    distance_operator_available: bool = False
    error: Optional[str] = None


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
