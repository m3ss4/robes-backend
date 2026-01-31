from app.services.search import SearchService


def test_search_returns_empty_for_unknown():
    service = SearchService()
    res = service.search_items("nothing", 5)
    assert res.hits == []
