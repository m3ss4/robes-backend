from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal


class DiversityPreferences(BaseModel):
    """User preferences for diversity scoring attributes."""
    colors: bool = False  # OFF by default per requirements
    patterns: bool = True
    seasons: bool = True
    styles: bool = True


class QualityPreferences(BaseModel):
    """User preferences for quality scoring."""
    diversity: DiversityPreferences = Field(default_factory=DiversityPreferences)
    refresh_interval_days: int = Field(default=7, ge=1, le=30)
    history_retention_days: int = Field(default=180, ge=30, le=730)


class QualityPreferencesUpdate(BaseModel):
    """Partial update for quality preferences."""
    diversity: Optional[DiversityPreferences] = None
    refresh_interval_days: Optional[int] = Field(default=None, ge=1, le=30)
    history_retention_days: Optional[int] = Field(default=None, ge=30, le=730)


class DimensionScore(BaseModel):
    """Score for a single dimension with explanation."""
    score: float = Field(..., ge=0, le=100, description="Score from 0-100")
    weight: float = Field(..., ge=0, le=1, description="Weight in total calculation")
    why: str = Field(..., description="Human-readable explanation")
    confidence: float = Field(..., ge=0, le=1, description="Confidence level 0-1")
    contributing_factors: Optional[List[str]] = None


class QualityScoreOut(BaseModel):
    """Quality score summary response."""
    id: str
    total_score: float = Field(..., ge=0, le=100)
    confidence: float = Field(..., ge=0, le=1)

    # Individual dimension scores with explanations
    versatility: DimensionScore
    utilization: DimensionScore
    completeness: DimensionScore
    balance: DimensionScore
    diversity: DimensionScore

    # Metadata
    items_count: int
    outfits_count: int
    wear_logs_count: int
    computed_at: str

    # Trend compared to previous score
    trend: Optional[Literal["improving", "stable", "declining"]] = None
    trend_delta: Optional[float] = None


class QualitySummaryOut(BaseModel):
    """Full quality summary with current score and history."""
    current: QualityScoreOut
    history: List[QualityScoreOut] = Field(default_factory=list)
    preferences: QualityPreferences


class SuggestionOut(BaseModel):
    """Single actionable suggestion."""
    id: str
    suggestion_type: str
    dimension: str
    priority: int = Field(..., ge=1, le=5)
    title: str
    description: str
    why: str
    confidence: float = Field(..., ge=0, le=1)
    expected_impact: Optional[float] = None
    related_item_ids: Optional[List[str]] = None
    status: Literal["pending", "dismissed", "completed"]
    created_at: str


class SuggestionsOut(BaseModel):
    """List of suggestions grouped by dimension."""
    suggestions: List[SuggestionOut]
    by_dimension: Dict[str, List[SuggestionOut]]
    total_count: int


class SuggestionDismissIn(BaseModel):
    """Request to dismiss a suggestion."""
    status: Literal["dismissed", "completed"]
