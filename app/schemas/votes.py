from pydantic import BaseModel, Field
from typing import List, Optional


class VoteSessionCreateIn(BaseModel):
    outfit_ids: List[str] = Field(default_factory=list)


class VoteSessionCreateOut(BaseModel):
    session_id: str
    share_code: str
    share_url: str
    created_at: Optional[str] = None


class VoteOutfitItemOut(BaseModel):
    item_id: str
    slot: str
    position: int = 0
    image_url: Optional[str] = None


class VoteSessionOutfitOut(BaseModel):
    outfit_id: str
    name: Optional[str] = None
    primary_image_url: Optional[str] = None
    vote_count: int = 0
    position: Optional[int] = None
    items: List[VoteOutfitItemOut] = Field(default_factory=list)


class VoteSessionOut(BaseModel):
    session_id: str
    share_code: str
    share_url: str
    created_at: Optional[str] = None
    outfits: List[VoteSessionOutfitOut]
    total_votes: int = 0


class VoteIn(BaseModel):
    outfit_id: str
    voter_hash: str


class VoteOut(BaseModel):
    session_id: str
    outfit_id: str
    vote_count: int
    total_votes: int
