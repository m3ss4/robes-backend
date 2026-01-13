from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AnyHttpUrl
from typing import List, Optional
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    APP_NAME: str = "Wardrobe OS API"
    APP_ENV: str = "dev"
    API_PREFIX: str = "/v1"
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "postgresql+psycopg://wardrobe:wardrobe@localhost:5432/wardrobe"
    REDIS_URL: str = "redis://localhost:6379/0"
    CORS_ORIGINS: str = "*"
    # LLM flags (default to disabled)
    LLM_ENABLED: bool = False
    LLM_PROVIDER: str = "local"
    LLM_MODEL_ATTRIBUTES: str = "gpt-4o-mini"
    LLM_MODEL_EXPLAIN: str = "gpt-4o-mini"
    LLM_SUGGEST_TIMEOUT_MS: int = 800
    LLM_ATTR_MIN_CONFIDENCE: float = 0.60
    LLM_TIEBREAK_EPS: float = 0.03
    LLM_CACHE_TTL_S: int = 604800
    LLM_USE_VISION: bool = False
    LLM_VISION_IMAGE_MAX: int = 1024
    LLM_VISION_URL_TTL_S: int = 300
    # Image processing switches
    IMGPROC_ENABLED: bool = True
    IMGPROC_ANALYSIS_MAX_SIDE: int = 1024
    IMGPROC_SAVE_BG_REMOVED: bool = True
    IMGPROC_FEATURES_VERSION: str = "v1"
    IMGPROC_EMBEDDINGS: str = "clip"
    CLIP_MODEL: str = "ViT-B-32"
    # Suggestion thresholds
    SUGGEST_TYPE_MIN_P: float = 0.60
    SUGGEST_PATTERN_MIN_P: float = 0.55
    SOLID_DOMINANCE_THR: float = 0.65
    EDGE_DENSITY_THR: float = 0.12
    STRIPE_THR: float = 0.08
    PLAID_THR: float = 0.05
    DOT_THR: float = 0.04

    @property
    def cors_origin_list(self) -> List[str]:
        val = self.CORS_ORIGINS
        if not val: return []
        if val == "*": return ["*"]
        return [v.strip() for v in val.split(",")]

settings = Settings()
