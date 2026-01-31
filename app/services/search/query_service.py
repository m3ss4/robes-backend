from app.services.search.service import SearchService


def query_items(service: SearchService, text: str, limit: int):
    return service.search_items(text, limit)
