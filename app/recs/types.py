from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Recommendation:
    id: str
    score: float
    reason: Optional[str] = None
