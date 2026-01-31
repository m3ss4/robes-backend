from app.services.recs import RecommendationService


def test_recs_returns_list():
    service = RecommendationService()
    res = service.recommend_items("user")
    assert isinstance(res, list)
