from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Notification:
    user_id: str
    title: str
    body: str
    channel: Optional[str] = None
