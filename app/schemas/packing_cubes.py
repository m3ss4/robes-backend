from pydantic import BaseModel
from typing import Optional, List, Literal


class PackingCubeIn(BaseModel):
    name: str
    type: Literal["virtual", "physical"]
    weather_tags: Optional[List[str]] = None
    location: Optional[str] = None


class PackingCubeOut(BaseModel):
    id: str
    name: str
    type: Literal["virtual", "physical"]
    weather_tags: Optional[List[str]] = None
    location: Optional[str] = None
    item_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PackingCubeItemIn(BaseModel):
    item_id: str


class PackingCubeItemOut(BaseModel):
    item_id: str
    name: Optional[str] = None
    category: Optional[str] = None
    type: Optional[str] = None
    image_url: Optional[str] = None


class PackingCubeDetailOut(BaseModel):
    id: str
    name: str
    type: Literal["virtual", "physical"]
    weather_tags: Optional[List[str]] = None
    location: Optional[str] = None
    items: List[PackingCubeItemOut]


class PackingCubeOwnershipOut(BaseModel):
    ownership: dict[str, str]
