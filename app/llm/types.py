from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field

Source = Literal["vision", "rule", "llm", "user", "locked"]


class SuggestField(BaseModel):
    value: Optional[object] = None
    confidence: float = 0.0
    source: Source = "llm"
    reason: Optional[str] = None


class SuggestDraft(BaseModel):
    category: SuggestField = Field(default_factory=SuggestField)
    type: SuggestField = Field(default_factory=SuggestField)
    base_color: SuggestField = Field(default_factory=SuggestField)
    tone: SuggestField = Field(default_factory=SuggestField)
    warmth: SuggestField = Field(default_factory=SuggestField)
    formality: SuggestField = Field(default_factory=SuggestField)
    layer_role: SuggestField = Field(default_factory=SuggestField)
    pattern: SuggestField = Field(default_factory=SuggestField)
    fabric_kind: SuggestField = Field(default_factory=SuggestField)
    material: SuggestField = Field(default_factory=SuggestField)
    season_tags: SuggestField = Field(default_factory=SuggestField)
    event_tags: SuggestField = Field(default_factory=SuggestField)
    style_tags: SuggestField = Field(default_factory=SuggestField)

    def lock(self, lock_fields: List[str]) -> None:
        for k in lock_fields or []:
            if hasattr(self, k):
                f: SuggestField = getattr(self, k)
                f.source = "user"
                f.confidence = max(f.confidence, 0.99)


class SuggestAmbiguity(BaseModel):
    clip_family_ambiguous: bool = False
    clip_pattern_ambiguous: bool = False


class LLMRequest(BaseModel):
    features: Dict[str, object] = Field(default_factory=dict)
    hints: Dict[str, object] = Field(default_factory=dict)
    lock_fields: List[str] = Field(default_factory=list)
    ambiguity: SuggestAmbiguity = Field(default_factory=SuggestAmbiguity)
    image_url: Optional[str] = None
