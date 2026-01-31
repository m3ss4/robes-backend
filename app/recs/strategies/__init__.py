from app.recs.strategies.base import Strategy
from app.recs.strategies.rules import RuleBasedStrategy
from app.recs.strategies.recent_wear import RecentWearStrategy
from app.recs.strategies.similar_color import SimilarColorStrategy
from app.recs.strategies.seasonal import SeasonalStrategy
from app.recs.strategies.diversity import DiversityStrategy

__all__ = [
    "Strategy",
    "RuleBasedStrategy",
    "RecentWearStrategy",
    "SimilarColorStrategy",
    "SeasonalStrategy",
    "DiversityStrategy",
]
