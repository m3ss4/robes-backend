from typing import List, Optional
from pydantic import BaseModel


class RecOut(BaseModel):
    id: str
    score: float
    reason: Optional[str] = None


class RecsOut(BaseModel):
    items: List[RecOut]
