from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class LLMUsage(BaseModel):
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cached: bool = False
    cache_key: Optional[str] = None
    prompt_version: str = "p1"


class SuggestFieldOut(BaseModel):
    value: Any = None
    confidence: float = 0.0
    source: str = "rules"  # rules | llm | both | locked
    rationale: Optional[str] = None


class SuggestItemAttributesInput(BaseModel):
    taxonomy: Dict[str, Any] = Field(default_factory=dict)
    features: Dict[str, Any] = Field(default_factory=dict)
    current: Dict[str, Any] = Field(default_factory=dict)
    locked: List[str] = Field(default_factory=list)
    allow_vision: bool = False
    image_url: Optional[str] = None
    prompt_version: str = "p1"


class SuggestItemAttributesOutput(BaseModel):
    suggestions: Dict[str, SuggestFieldOut] = Field(default_factory=dict)
    usage: LLMUsage = Field(default_factory=LLMUsage)


class ExplainOutfitInput(BaseModel):
    metrics: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)
    items: List[Dict[str, Any]] = Field(default_factory=list)
    prompt_version: str = "p1"
    compare: bool = False


class ExplainOutfitOutput(BaseModel):
    explanations: List[str] = Field(default_factory=list)
    tiebreak: Optional[str] = None
    usage: LLMUsage = Field(default_factory=LLMUsage)


class PairingCandidate(BaseModel):
    item_id: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    attribute_sources: Dict[str, Any] = Field(default_factory=dict)


class SuggestItemPairingsInput(BaseModel):
    base_item: Dict[str, Any] = Field(default_factory=dict)
    candidates: List[PairingCandidate] = Field(default_factory=list)
    limit: int = 10
    prompt_version: str = "p1"


class PairingSuggestionOut(BaseModel):
    item_id: str
    score: float


class SuggestItemPairingsOutput(BaseModel):
    suggestions: List[PairingSuggestionOut] = Field(default_factory=list)
    usage: LLMUsage = Field(default_factory=LLMUsage)


class AskUserItemsInput(BaseModel):
    question: str
    items: List[Dict[str, Any]] = Field(default_factory=list)
    prompt_version: str = "p1"


class AskUserItemsOutput(BaseModel):
    answer: str = ""
    usage: LLMUsage = Field(default_factory=LLMUsage)
