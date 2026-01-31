from app.recs.config import RecsConfig
from app.recs.strategies.rules import RuleBasedStrategy
from app.recs.strategies.recent_wear import RecentWearStrategy
from app.recs.strategies.similar_color import SimilarColorStrategy
from app.recs.strategies.seasonal import SeasonalStrategy
from app.recs.strategies.diversity import DiversityStrategy
from app.recs.types import Recommendation


class RecommendationService:
    def __init__(self, config: RecsConfig | None = None) -> None:
        self.config = config or RecsConfig()
        self.strategies = [
            RuleBasedStrategy(),
            RecentWearStrategy(),
            SimilarColorStrategy(),
            SeasonalStrategy(),
            DiversityStrategy(),
        ]

    def recommend_items(self, user_id: str):
        return self._run(user_id)

    def recommend_outfits(self, user_id: str):
        return self._run(user_id)

    def _run(self, user_id: str):
        recs: list[Recommendation] = []
        for strategy in self.strategies:
            for rec_id, score in strategy.recommend(user_id):
                recs.append(Recommendation(id=rec_id, score=score, reason=strategy.name))
        return recs[: self.config.max_results]
