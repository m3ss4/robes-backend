from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class DimensionResult:
    """Result from scoring a single dimension."""
    score: float  # 0-100
    confidence: float  # 0-1
    why: str
    contributing_factors: List[str] = field(default_factory=list)


@dataclass
class ScoringContext:
    """Context data for scoring calculations."""
    user_id: str
    items: List[Any]  # Item models
    outfits: List[Any]  # Outfit models
    wear_logs: List[Any]  # OutfitWearLog models
    item_wear_logs: List[Any]  # ItemWearLog models
    outfit_wear_log_items: List[Any]  # OutfitWearLogItem models (items worn via outfit logs)
    diversity_config: Dict[str, bool]

    @property
    def items_count(self) -> int:
        return len(self.items)

    @property
    def outfits_count(self) -> int:
        return len(self.outfits)

    @property
    def wear_logs_count(self) -> int:
        return len(self.wear_logs) + len(self.item_wear_logs)


@dataclass
class SuggestionData:
    """Data for a generated suggestion."""
    suggestion_type: str
    dimension: str
    priority: int
    title: str
    description: str
    why: str
    confidence: float
    expected_impact: Optional[float] = None
    related_item_ids: Optional[List[str]] = None
